import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .roles import ROLE_CATALOG


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
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS user_profiles (
                telegram_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL DEFAULT '',
                file_id TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS user_resumes (
                telegram_id TEXT NOT NULL,
                profile_key TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                file_id TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, profile_key)
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS user_preferences (
                telegram_id TEXT PRIMARY KEY,
                roles TEXT NOT NULL DEFAULT 'qa',
                threshold REAL NOT NULL DEFAULT 0.60,
                language_mode TEXT NOT NULL DEFAULT 'ru_tech',
                auto_search_enabled INTEGER NOT NULL DEFAULT 0,
                work_format TEXT NOT NULL DEFAULT 'remote',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS user_sent_jobs (
                telegram_id TEXT NOT NULL,
                url TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, url)
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS user_search_stats (
                telegram_id TEXT PRIMARY KEY,
                search_count INTEGER NOT NULL DEFAULT 0,
                jobs_collected INTEGER NOT NULL DEFAULT 0,
                jobs_matched INTEGER NOT NULL DEFAULT 0,
                jobs_sent INTEGER NOT NULL DEFAULT 0,
                last_search_at TEXT DEFAULT ''
            )"""
        )
        if not self.is_postgres:
            self._ensure_user_column("rejection_attempts", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_user_column("retry_after", "TEXT NOT NULL DEFAULT ''")
            self._ensure_preference_column("language_mode", "TEXT NOT NULL DEFAULT 'ru_tech'")
            self._ensure_preference_column("auto_search_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_preference_column("work_format", "TEXT NOT NULL DEFAULT 'remote'")
        else:
            self.db.execute(
                "ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS language_mode TEXT NOT NULL DEFAULT 'ru_tech'"
            )
            self.db.execute(
                "ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS auto_search_enabled INTEGER NOT NULL DEFAULT 0"
            )
            self.db.execute(
                "ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS work_format TEXT NOT NULL DEFAULT 'remote'"
            )
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

    def _ensure_preference_column(self, name: str, definition: str) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(user_preferences)")}
        if name not in columns:
            self.db.execute(f"ALTER TABLE user_preferences ADD COLUMN {name} {definition}")

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
        count += self.db.execute("SELECT COUNT(*) FROM user_sent_jobs").fetchone()[0]
        self.db.execute("DELETE FROM sent_jobs")
        self.db.execute("DELETE FROM user_sent_jobs")
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
        self.db.execute(self._sql("DELETE FROM user_profiles WHERE telegram_id = ?"), (telegram_id,))
        self.db.execute(self._sql("DELETE FROM user_resumes WHERE telegram_id = ?"), (telegram_id,))
        self.db.execute(self._sql("DELETE FROM user_preferences WHERE telegram_id = ?"), (telegram_id,))
        self.db.execute(self._sql("DELETE FROM user_sent_jobs WHERE telegram_id = ?"), (telegram_id,))
        self.db.execute(self._sql("DELETE FROM user_search_stats WHERE telegram_id = ?"), (telegram_id,))
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

    def save_profile(
        self,
        telegram_id: str,
        filename: str,
        file_id: str,
        profile: dict,
        profile_key: str = "default",
    ) -> None:
        self.db.execute(
            self._sql(
                """INSERT INTO user_resumes(telegram_id, profile_key, filename, file_id, profile_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_id, profile_key) DO UPDATE SET
                       filename = excluded.filename,
                       file_id = excluded.file_id,
                       profile_json = excluded.profile_json,
                       updated_at = CURRENT_TIMESTAMP"""
            ),
            (telegram_id, profile_key, filename, file_id, json.dumps(profile, ensure_ascii=False)),
        )
        self.db.commit()

    @staticmethod
    def _profile_record(row) -> dict:
        return {"profile_key": row[0], "filename": row[1], "file_id": row[2], "profile": json.loads(row[3]), "updated_at": row[4]}

    def list_profiles(self, telegram_id: str) -> list[dict]:
        rows = self.db.execute(
            self._sql(
                "SELECT profile_key, filename, file_id, profile_json, updated_at "
                "FROM user_resumes WHERE telegram_id = ? ORDER BY profile_key"
            ),
            (telegram_id,),
        ).fetchall()
        profiles = [self._profile_record(row) for row in rows]
        # Preserve the original single-profile records created before the
        # role-specific resume feature was introduced.
        if not any(item["profile_key"] == "default" for item in profiles):
            legacy = self.db.execute(
                self._sql("SELECT filename, file_id, profile_json, updated_at FROM user_profiles WHERE telegram_id = ?"),
                (telegram_id,),
            ).fetchone()
            if legacy:
                profiles.insert(0, {"profile_key": "default", "filename": legacy[0], "file_id": legacy[1], "profile": json.loads(legacy[2]), "updated_at": legacy[3]})
        return profiles

    def get_profile(self, telegram_id: str, profile_key: str = "default") -> dict | None:
        row = self.db.execute(
            self._sql("SELECT profile_key, filename, file_id, profile_json, updated_at FROM user_resumes WHERE telegram_id = ? AND profile_key = ?"),
            (telegram_id, profile_key),
        ).fetchone()
        if row:
            return self._profile_record(row)
        if profile_key != "default":
            return None
        legacy = self.db.execute(
            self._sql("SELECT filename, file_id, profile_json, updated_at FROM user_profiles WHERE telegram_id = ?"),
            (telegram_id,),
        ).fetchone()
        if not legacy:
            return None
        return {"profile_key": "default", "filename": legacy[0], "file_id": legacy[1], "profile": json.loads(legacy[2]), "updated_at": legacy[3]}

    def get_profile_for_role(self, telegram_id: str, role: str) -> dict | None:
        return self.get_profile(telegram_id, role) or self.get_profile(telegram_id, "default")

    def get_preferences(self, telegram_id: str) -> dict:
        row = self.db.execute(
            self._sql("SELECT roles, threshold, language_mode, auto_search_enabled, work_format FROM user_preferences WHERE telegram_id = ?"),
            (telegram_id,),
        ).fetchone()
        if not row:
            return {
                "roles": ("qa",),
                "threshold": 0.60,
                "language_mode": "ru_tech",
                "auto_search_enabled": False,
                "work_format": "remote",
            }
        roles = tuple(dict.fromkeys(role for role in row[0].split(",") if role in ROLE_CATALOG))
        language_mode = row[2] if row[2] in {"ru", "ru_tech", "any"} else "ru_tech"
        return {
            "roles": roles or ("qa",),
            "threshold": float(row[1]),
            "language_mode": language_mode,
            "auto_search_enabled": bool(row[3]),
            "work_format": row[4] if row[4] in {"remote", "office"} else "remote",
        }

    def save_preferences(
        self,
        telegram_id: str,
        roles: tuple[str, ...],
        threshold: float,
        language_mode: str = "ru_tech",
        auto_search_enabled: bool = False,
        work_format: str = "remote",
    ) -> None:
        selected_roles = tuple(dict.fromkeys(role for role in roles if role in ROLE_CATALOG)) or ("qa",)
        if language_mode not in {"ru", "ru_tech", "any"}:
            language_mode = "ru_tech"
        if work_format not in {"remote", "office"}:
            work_format = "remote"
        self.db.execute(
            self._sql(
                """INSERT INTO user_preferences(telegram_id, roles, threshold, language_mode, auto_search_enabled, work_format)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET
                       roles = excluded.roles,
                       threshold = excluded.threshold,
                       language_mode = excluded.language_mode,
                       auto_search_enabled = excluded.auto_search_enabled,
                       work_format = excluded.work_format,
                       updated_at = CURRENT_TIMESTAMP"""
            ),
            (telegram_id, ",".join(selected_roles), threshold, language_mode, int(auto_search_enabled), work_format),
        )
        self.db.commit()

    def already_sent_for_user(self, telegram_id: str, url: str) -> bool:
        return self.db.execute(
            self._sql("SELECT 1 FROM user_sent_jobs WHERE telegram_id = ? AND url = ?"),
            (telegram_id, url),
        ).fetchone() is not None

    def mark_sent_for_user(self, telegram_id: str, url: str) -> None:
        query = (
            "INSERT INTO user_sent_jobs(telegram_id, url) VALUES (%s, %s) ON CONFLICT DO NOTHING"
            if self.is_postgres
            else "INSERT OR IGNORE INTO user_sent_jobs(telegram_id, url) VALUES (?, ?)"
        )
        self.db.execute(query, (telegram_id, url))
        self.db.commit()

    def record_search_stats(
        self,
        telegram_id: str,
        jobs_collected: int,
        jobs_matched: int,
        jobs_sent: int,
    ) -> None:
        query = self._sql(
            """INSERT INTO user_search_stats(
                   telegram_id, search_count, jobs_collected, jobs_matched, jobs_sent, last_search_at
               ) VALUES (?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   search_count = user_search_stats.search_count + 1,
                   jobs_collected = user_search_stats.jobs_collected + excluded.jobs_collected,
                   jobs_matched = user_search_stats.jobs_matched + excluded.jobs_matched,
                   jobs_sent = user_search_stats.jobs_sent + excluded.jobs_sent,
                   last_search_at = CURRENT_TIMESTAMP"""
        )
        self.db.execute(query, (telegram_id, jobs_collected, jobs_matched, jobs_sent))
        self.db.commit()

    def get_search_stats(self, telegram_id: str) -> dict:
        row = self.db.execute(
            self._sql(
                "SELECT search_count, jobs_collected, jobs_matched, jobs_sent, last_search_at "
                "FROM user_search_stats WHERE telegram_id = ?"
            ),
            (telegram_id,),
        ).fetchone()
        if not row:
            return {
                "search_count": 0,
                "jobs_collected": 0,
                "jobs_matched": 0,
                "jobs_sent": 0,
                "last_search_at": "",
            }
        return dict(zip(("search_count", "jobs_collected", "jobs_matched", "jobs_sent", "last_search_at"), row))
