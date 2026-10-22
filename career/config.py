import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    root: Path
    resume_dir: Path
    threshold: float
    interval_hours: float
    timeout: float
    database_path: Path
    telegram_token: str
    telegram_chat_id: str
    extra_skills: tuple[str, ...]


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    database = Path(os.getenv("DATABASE_PATH", "career.db"))
    if not database.is_absolute():
        database = root / database
    return Settings(
        root=root,
        resume_dir=root / "resumes",
        threshold=float(os.getenv("MATCH_THRESHOLD", "0.30")),
        interval_hours=float(os.getenv("SEARCH_INTERVAL_HOURS", "6")),
        timeout=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        database_path=database,
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        extra_skills=tuple(x.strip().lower() for x in os.getenv("EXTRA_SKILLS", "").split(",") if x.strip()),
    )
