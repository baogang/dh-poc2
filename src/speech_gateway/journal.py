"""M12/M13: bounded metadata journal; transcripts and credentials never stored."""
import sqlite3
import time
import threading
from pathlib import Path
from collections import Counter


class Journal:
    def __init__(self, path):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS events(at REAL, session TEXT, kind TEXT, epoch INTEGER)")
        self.counts = Counter()

    def record(self, session, kind, epoch):
        with self.lock:
            self.counts[kind] += 1
            self.db.execute("INSERT INTO events VALUES(?,?,?,?)", (time.time(), session, kind, epoch))
            self.db.execute("DELETE FROM events WHERE rowid <= (SELECT MAX(rowid)-10000 FROM events)")
            self.db.commit()

    def close(self):
        self.db.close()
