import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS sent_jobs (url TEXT PRIMARY KEY, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.db.commit()

    def already_sent(self, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM sent_jobs WHERE url = ?", (url,)).fetchone() is not None

    def mark_sent(self, url: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO sent_jobs(url) VALUES (?)", (url,))
        self.db.commit()

    def clear_sent(self) -> int:
        count = self.db.execute("SELECT COUNT(*) FROM sent_jobs").fetchone()[0]
        self.db.execute("DELETE FROM sent_jobs")
        self.db.commit()
        return count

    def upsert_user(self, telegram_id: str, username: str = "", phone: str = "") -> None:
        self.db.execute(
            """INSERT INTO bot_users(telegram_id, username, phone)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   username = excluded.username,
                   phone = CASE WHEN excluded.phone <> '' THEN excluded.phone ELSE bot_users.phone END,
                   updated_at = CURRENT_TIMESTAMP""",
            (telegram_id, username, phone),
        )
        self.db.commit()

    def get_user(self, telegram_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT telegram_id, username, phone, status, created_at, updated_at FROM bot_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("telegram_id", "username", "phone", "status", "created_at", "updated_at")
        return dict(zip(keys, row))

    def set_user_status(self, telegram_id: str, status: str) -> None:
        self.db.execute(
            "UPDATE bot_users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            (status, telegram_id),
        )
        self.db.commit()

    def list_users(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT telegram_id, username, phone, status, created_at, updated_at FROM bot_users ORDER BY created_at"
        ).fetchall()
        keys = ("telegram_id", "username", "phone", "status", "created_at", "updated_at")
        return [dict(zip(keys, row)) for row in rows]
