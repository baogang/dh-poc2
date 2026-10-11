"""POSIX evaluation ledger: lock, atomic replace and fsync BEFORE paid network I/O.

Timeouts/cancellation retain unknown cost. No credentials are accepted or stored.
"""
import contextlib
import fcntl
import json
import math
import os
import tempfile
import uuid
from pathlib import Path


def _money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid budget amount')
    return float(value)


class Budget:
    def __init__(self, path, cap=5):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            if not self.path.exists():
                self._write({'cap': _money(cap), 'committed': 0., 'actual': 0., 'unknown': 0, 'calls': []})
            if self._read()['cap'] != _money(cap):
                raise ValueError('cap differs from existing authorization')

    @contextlib.contextmanager
    def _lock(self):
        with self.path.with_suffix(self.path.suffix+'.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        try:
            data = json.loads(self.path.read_text())
            cap = _money(data['cap'])
            calls = data['calls']
            if not isinstance(calls, list):
                raise ValueError()
            ids, committed, actual, unknown = set(), 0., 0., 0
            for index, call in enumerate(calls):
                # Migrate historical calls without resetting any occupied budget.
                call.setdefault('call_id', 'legacy-'+str(index))
                cost = call.get('reported_cost_usd')
                call.setdefault('state', 'settled' if cost is not None else 'unknown')
                if call['call_id'] in ids or call['state'] not in {'pending', 'unknown', 'settled'}:
                    raise ValueError()
                ids.add(call['call_id'])
                reserved = _money(call['reserved_usd'])
                if cost is not None:
                    cost = _money(cost)
                    if call['state'] != 'settled':
                        raise ValueError()
                    actual += cost
                    committed += cost
                else:
                    if call['state'] == 'settled':
                        raise ValueError()
                    committed += reserved
                    unknown += 1
            for name, value in [('committed', committed), ('actual', actual), ('unknown', unknown)]:
                if not math.isclose(_money(data[name]), value, abs_tol=1e-9):
                    raise ValueError()
            data.update(cap=cap, committed=committed, actual=actual, unknown=unknown)
            return data
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('invalid ledger; refusing paid requests') from exc

    def _write(self, data):
        fd, temp = tempfile.mkstemp(prefix=self.path.name+'.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as file:
                json.dump(data, file, indent=2, allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def snapshot(self):
        with self._lock():
            return self._read()

    def reserve(self, amount, model):
        amount = _money(amount)
        if not amount:
            raise ValueError('reservation must be positive')
        with self._lock():
            data = self._read()
            if data['committed']+amount > data['cap']+1e-9:
                raise RuntimeError('budget exhausted')
            call_id = str(uuid.uuid4())
            data['calls'].append({'call_id': call_id, 'model': model, 'state': 'pending',
                                  'reserved_usd': amount, 'reported_cost_usd': None})
            data['committed'] += amount
            data['unknown'] += 1
            self._write(data)
            return call_id

    def settle(self, call_id, usage):
        cost = usage.get('cost') if isinstance(usage, dict) else None
        if cost is not None:
            cost = _money(cost)
        with self._lock():
            data = self._read()
            call = next((x for x in data['calls'] if x['call_id'] == call_id), None)
            if call is None or call['state'] != 'pending':
                raise ValueError('unknown or already settled call')
            call['state'] = 'unknown' if cost is None else 'settled'
            call['reported_cost_usd'] = cost
            if cost is not None:
                data['committed'] += cost-call['reserved_usd']
                data['actual'] += cost
                data['unknown'] -= 1
            self._write(data)
