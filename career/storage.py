import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS sent_jobs (url TEXT PRIMARY KEY, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.db.commit()

    def already_sent(self, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM sent_jobs WHERE url = ?", (url,)).fetchone() is not None

    def mark_sent(self, url: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO sent_jobs(url) VALUES (?)", (url,))
        self.db.commit()
