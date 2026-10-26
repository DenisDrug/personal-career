import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Storage:
    def __init__(self, path: Path, database_url: str = ""):
        self.is_postgres = bool(database_url)
        if self.is_postgres:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("PostgreSQL support requires the psycopg package") from exc
            self.db = psycopg.connect(database_url)
        else:
            self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS sent_jobs (url TEXT PRIMARY KEY, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                rejection_attempts INTEGER NOT NULL DEFAULT 0,
                retry_after TEXT NOT NULL DEFAULT ''
            )"""
        )
        if not self.is_postgres:
            self._ensure_user_column("rejection_attempts", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_user_column("retry_after", "TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    @property
    def placeholder(self) -> str:
        return "%s" if self.is_postgres else "?"

    def _sql(self, query: str) -> str:
        return query.replace("?", self.placeholder)

    def _ensure_user_column(self, name: str, definition: str) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(bot_users)")}
        if name not in columns:
            self.db.execute(f"ALTER TABLE bot_users ADD COLUMN {name} {definition}")

    def already_sent(self, url: str) -> bool:
        return self.db.execute(f"SELECT 1 FROM sent_jobs WHERE url = {self.placeholder}", (url,)).fetchone() is not None

    def mark_sent(self, url: str) -> None:
        query = (
            "INSERT INTO sent_jobs(url) VALUES (%s) ON CONFLICT(url) DO NOTHING"
            if self.is_postgres
            else "INSERT OR IGNORE INTO sent_jobs(url) VALUES (?)"
        )
        self.db.execute(query, (url,))
        self.db.commit()

    def clear_sent(self) -> int:
        count = self.db.execute("SELECT COUNT(*) FROM sent_jobs").fetchone()[0]
        self.db.execute("DELETE FROM sent_jobs")
        self.db.commit()
        return count

    def upsert_user(self, telegram_id: str, username: str = "", phone: str = "") -> None:
        self.db.execute(
            f"""INSERT INTO bot_users(telegram_id, username, phone)
               VALUES ({self.placeholder}, {self.placeholder}, {self.placeholder})
               ON CONFLICT(telegram_id) DO UPDATE SET
                   username = excluded.username,
                   phone = CASE WHEN excluded.phone <> '' THEN excluded.phone ELSE bot_users.phone END,
                   updated_at = CURRENT_TIMESTAMP""",
            (telegram_id, username, phone),
        )
        self.db.commit()

    def get_user(self, telegram_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT telegram_id, username, phone, status, created_at, updated_at, rejection_attempts, retry_after "
            f"FROM bot_users WHERE telegram_id = {self.placeholder}",
            (telegram_id,),
        ).fetchone()
        if not row:
            return None
        keys = (
            "telegram_id",
            "username",
            "phone",
            "status",
            "created_at",
            "updated_at",
            "rejection_attempts",
            "retry_after",
        )
        return dict(zip(keys, row))

    def set_user_status(self, telegram_id: str, status: str) -> None:
        reset_attempts = status == "approved"
        self.db.execute(
            self._sql("UPDATE bot_users SET status = ?, rejection_attempts = CASE WHEN ? THEN 0 ELSE rejection_attempts END, "
            "retry_after = CASE WHEN ? THEN '' ELSE retry_after END, updated_at = CURRENT_TIMESTAMP "
            "WHERE telegram_id = ?"),
            (status, reset_attempts, reset_attempts, telegram_id),
        )
        self.db.commit()

    def request_access(self, telegram_id: str) -> bool:
        """Move a rejected user back to pending unless the 30-day cooldown is active."""
        user = self.get_user(telegram_id)
        if not user or user["status"] != "rejected":
            return False

        now = datetime.now(timezone.utc)
        retry_after_text = user.get("retry_after", "")
        retry_after = None
        if retry_after_text:
            try:
                retry_after = datetime.fromisoformat(retry_after_text)
                if retry_after.tzinfo is None:
                    retry_after = retry_after.replace(tzinfo=timezone.utc)
            except ValueError:
                retry_after = None

        if retry_after and retry_after > now:
            return False

        should_reset = bool(retry_after) or user["rejection_attempts"] >= 3
        self.db.execute(
            self._sql("UPDATE bot_users SET status = 'pending', rejection_attempts = CASE WHEN ? THEN 0 ELSE rejection_attempts END, "
            "retry_after = '', updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?"),
            (should_reset, telegram_id),
        )
        self.db.commit()
        return True

    def reject_user(self, telegram_id: str) -> dict | None:
        """Reject a user and start a cooldown after the third rejection."""
        user = self.get_user(telegram_id)
        if not user:
            return None
        attempts = int(user.get("rejection_attempts", 0)) + 1
        retry_after = ""
        if attempts >= 3:
            retry_after = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        self.db.execute(
            self._sql("UPDATE bot_users SET status = 'rejected', rejection_attempts = ?, retry_after = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?"),
            (attempts, retry_after, telegram_id),
        )
        self.db.commit()
        return self.get_user(telegram_id)

    def delete_user(self, telegram_id: str) -> bool:
        cursor = self.db.execute(self._sql("DELETE FROM bot_users WHERE telegram_id = ?"), (telegram_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def list_users(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT telegram_id, username, phone, status, created_at, updated_at, rejection_attempts, retry_after "
            "FROM bot_users ORDER BY created_at"
        ).fetchall()
        keys = (
            "telegram_id",
            "username",
            "phone",
            "status",
            "created_at",
            "updated_at",
            "rejection_attempts",
            "retry_after",
        )
        return [dict(zip(keys, row)) for row in rows]
