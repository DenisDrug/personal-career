import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    root: Path
    resume_dir: Path
    threshold: float
    search_times: tuple[tuple[int, int], ...]
    timezone_name: str
    timeout: float
    database_path: Path
    database_url: str
    telegram_token: str
    telegram_chat_id: str
    admin_chat_ids: tuple[str, ...]
    admin_user_ids: tuple[str, ...]
    extra_skills: tuple[str, ...]


def _parse_search_times(value: str) -> tuple[tuple[int, int], ...]:
    times = []
    for item in value.split(","):
        hour_text, minute_text = item.strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(f"Invalid search time: {item!r}")
        times.append((hour, minute))
    if not times:
        raise ValueError("At least one search time is required")
    return tuple(sorted(set(times)))


def _parse_chat_ids(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
        search_times=_parse_search_times(os.getenv("SEARCH_TIMES", "08:00,12:00,16:00,18:00")),
        timezone_name=os.getenv("SEARCH_TIMEZONE", "Europe/Minsk"),
        timeout=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        database_path=database,
        database_url=os.getenv("DATABASE_URL", "").strip(),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        admin_chat_ids=_parse_chat_ids(os.getenv("ADMIN_CHAT_IDS", "")) or _parse_chat_ids(os.getenv("TELEGRAM_CHAT_ID", "")),
        admin_user_ids=_parse_chat_ids(os.getenv("ADMIN_USER_IDS", "")) or _parse_chat_ids(os.getenv("TELEGRAM_CHAT_ID", "")),
        extra_skills=tuple(x.strip().lower() for x in os.getenv("EXTRA_SKILLS", "").split(",") if x.strip()),
    )
