"""M07: single conversation owner, epoch fencing, cancellation and bounded admission."""
import asyncio
import contextlib
import secrets
from .codec import wav_bytes
from .text import speech_chunks


class Admission:
    def __init__(self, maximum):
        self.maximum, self.active = maximum, set()

    def acquire(self):
        if len(self.active) >= self.maximum:
            return None
        sid = secrets.token_hex(16)
        self.active.add(sid)
        return sid

    def release(self, sid):
        self.active.discard(sid)


class Session:
    def __init__(self, sid, providers, send, send_audio, journal, semaphore):
        self.sid, self.providers, self.send, self.send_audio = sid, providers, send, send_audio
        self.journal, self.semaphore = journal, semaphore
        self.epoch, self.task, self.closed = 0, None, False
        self.transferred = False
        self.tasks = set()
        self.send_lock = asyncio.Lock()

    async def interrupt(self):
        # Fencing happens before waiting for cancellation: old producers cannot revive output.
        self.epoch += 1
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        async with self.send_lock:
            await self.send({"type": "stop", "epoch": self.epoch})
        self.journal.record(self.sid, "interrupt", self.epoch)

    async def submit(self, pcm):
        if self.closed or self.transferred:
            return
        await self.interrupt()
        self.task = asyncio.create_task(self.run_turn(pcm, self.epoch))
        self.tasks.add(self.task)
        self.task.add_done_callback(self.tasks.discard)

    async def handoff(self, reason):
        if self.closed or self.transferred:
            return
        await self.interrupt()
        self.transferred = True
        await self.guarded({"type": "handoff", "reason": reason}, self.epoch)
        self.journal.record(self.sid, "handoff_requested", self.epoch)

    async def guarded(self, event, epoch):
        async with self.send_lock:
            if self.closed or epoch != self.epoch:
                return False
            await self.send({**event, "epoch": epoch})
            return True

    async def run_turn(self, pcm, epoch):
        try:
            # Finite queue wait; overload produces a channel event, never unbounded backlog.
            async with asyncio.timeout(2):
                await self.semaphore.acquire()
            try:
                async with asyncio.timeout(60):
                    text = await self.providers.asr(wav_bytes(pcm))
                    if not await self.guarded({"type": "transcript", "text": text}, epoch):
                        return
                    if not text:
                        await self.guarded({"type": "clarify", "reason": "empty_asr"}, epoch)
                        return
                    result = await self.providers.business(self.sid, text)
                    if result["handoff"]:
                        if epoch != self.epoch or self.closed:
                            return
                        self.transferred = True
                        await self.guarded({"type": "handoff", "reason": result.get("reason", "business")}, epoch)
                        self.journal.record(self.sid, "handoff_requested", epoch)
                        return
                    if not await self.guarded({"type": "reply", "text": result["reply"]}, epoch):
                        return
                    for sentence in speech_chunks(result["reply"], result.get("speech_slots")):
                        if self.closed or self.transferred or epoch != self.epoch:
                            return
                        audio = await self.providers.tts(sentence)
                        if self.closed or self.transferred or epoch != self.epoch:
                            return
                        # 20ms PCM frames and paced output; stop has a chance to acquire send_lock.
                        for offset in range(0, len(audio), 640):
                            async with self.send_lock:
                                if self.closed or epoch != self.epoch:
                                    return
                                await self.send_audio(audio[offset:offset+640], epoch)
                            await asyncio.sleep(.02)
                    await self.guarded({"type": "done"}, epoch)
                    self.journal.record(self.sid, "turn_complete", epoch)
            finally:
                self.semaphore.release()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not expose URLs, Authorization headers, or upstream error text.
            await self.guarded({"type": "error", "reason": "overload" if isinstance(exc, TimeoutError) else "upstream_failure"}, epoch)
            self.journal.record(self.sid, "turn_failed", epoch)

    async def close(self):
        self.closed = True
        self.epoch += 1
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                async with asyncio.timeout(5):
                    await asyncio.gather(*self.tasks, return_exceptions=True)
