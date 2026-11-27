import argparse
import sqlite3
from pathlib import Path

from .config import load_settings
from .storage import Storage


def migrate_sqlite_to_postgres(source_path: Path, database_url: str) -> tuple[int, int]:
    """Copy the existing SQLite data into PostgreSQL without deleting the source."""
    if not database_url:
        raise ValueError("DATABASE_URL is required for the migration")

    source = sqlite3.connect(source_path)
    target = Storage(source_path, database_url)
    sent_rows = source.execute("SELECT url, sent_at FROM sent_jobs ORDER BY url").fetchall()
    user_rows = source.execute(
        "SELECT telegram_id, username, phone, status, created_at, updated_at, rejection_attempts, retry_after "
        "FROM bot_users ORDER BY telegram_id"
    ).fetchall()

    for url, sent_at in sent_rows:
        target.db.execute(
            "INSERT INTO sent_jobs(url, sent_at) VALUES (%s, %s) ON CONFLICT(url) DO NOTHING",
            (url, sent_at),
        )
    for row in user_rows:
        target.db.execute(
            """INSERT INTO bot_users(
                telegram_id, username, phone, status, created_at, updated_at,
                rejection_attempts, retry_after
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                phone = EXCLUDED.phone,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                rejection_attempts = EXCLUDED.rejection_attempts,
                retry_after = EXCLUDED.retry_after""",
            row,
        )
    target.db.commit()
    source.close()
    target.db.close()
    return len(sent_rows), len(user_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate personal-career SQLite data to PostgreSQL")
    parser.add_argument("--source", type=Path, default=Path("career.db"))
    args = parser.parse_args()
    settings = load_settings()
    sent_count, user_count = migrate_sqlite_to_postgres(args.source, settings.database_url)
    print(f"Migrated sent_jobs={sent_count}, bot_users={user_count}")


if __name__ == "__main__":
    main()
