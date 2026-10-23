import argparse
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import load_settings
from .matcher import match_job, role_for_title
from .resumes import load_profile
from .sources import search_all
from .storage import Storage
from .telegram import send_match


RUSSIAN_LOCATION_MARKERS = (
    "россия",
    "russia",
    "рф",
    "москва",
    "санкт-петербург",
    "санкт петербург",
    "спб",
    "екатеринбург",
    "новосибирск",
    "нижний новгород",
    "казань",
    "самара",
    "омск",
    "уфа",
    "красноярск",
    "пермь",
    "воронеж",
    "ростов-на-дону",
    "ростов на дону",
    "краснодар",
    "сочи",
    "волгоград",
    "челябинск",
    "тюмень",
    "владивосток",
    "иркутск",
    "калининград",
    "хабаровск",
)
REMOTE_MARKERS = (
    "удалённ",
    "удаленн",
    "удалёнка",
    "удаленка",
    "дистанционн",
    "remote",
    "work from home",
    "работа из дома",
    "из дома",
)
NON_REMOTE_MARKERS = (
    "гибрид",
    "hybrid",
    "в офисе",
    "на месте",
    "офисный формат",
    "офисная работа",
)


def _has_location_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text) for marker in markers)


def is_russian_remote_job(job) -> bool:
    """Return whether a Russian vacancy explicitly offers fully remote work."""
    location = (job.location or "").lower()
    text = f"{location} {job.title} {job.description}".lower()
    if not _has_location_marker(text, RUSSIAN_LOCATION_MARKERS):
        return True

    if re.search(r"не\s+(?:полностью\s+)?удал[её]нн|без\s+удал[её]нн", text):
        return False
    if _has_location_marker(text, NON_REMOTE_MARKERS):
        return False
    return any(marker in text for marker in REMOTE_MARKERS)


def is_russian_job(job) -> bool:
    """Keep Russian-language vacancies; English tech terms are allowed inside them."""
    language = job.language.lower()
    if language and any(marker in language for marker in ("en", "english", "англ")) and not any(
        marker in language for marker in ("ru", "russian", "рус")
    ):
        return False
    text = f"{job.title} {job.description}".lower()
    cyrillic = len(re.findall(r"[а-яё]", text.lower()))
    latin = len(re.findall(r"[a-z]", text.lower()))
    # Require a substantial Russian description. English tool names, stack names,
    # and documentation terms remain valid inside an otherwise Russian vacancy.
    return cyrillic >= 40 and cyrillic / max(cyrillic + latin, 1) >= 0.25


def run_once(since: datetime | None = None, chat_id: str | None = None, role: str | None = None, skip_sent: bool = True, mark_sent: bool = True) -> int:
    settings = load_settings()
    profile = load_profile(settings.resume_dir, settings.extra_skills)
    jobs = search_all(settings.timeout, since=since, role=role)
    storage = Storage(settings.database_path)
    russian_jobs = 0
    matched_jobs = 0
    sent = 0
    for job in jobs:
        if skip_sent and storage.already_sent(job.url):
            continue
        if role and role_for_title(job.title) != role:
            continue
        if not is_russian_job(job):
            continue
        if not is_russian_remote_job(job):
            continue
        russian_jobs += 1
        match = match_job(job, profile)
        if match.score < settings.threshold:
            continue
        matched_jobs += 1
        try:
            send_match(settings.telegram_token, chat_id or settings.telegram_chat_id, match, settings.timeout)
        except Exception as exc:
            print(f"Telegram notification failed for {job.url}: {exc}")
            continue
        if mark_sent:
            storage.mark_sent(job.url)
        sent += 1
    print(f"Collected {len(jobs)} jobs, Russian {russian_jobs}, matched {matched_jobs}, sent {sent} notifications")
    return sent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run one search and exit")
    parser.add_argument("--interval-hours", type=float, default=None)
    args = parser.parse_args()
    settings = load_settings()
    if args.once:
        run_once()
        return
    if settings.telegram_token:
        from .bot import run_bot

        threading.Thread(target=run_bot, args=(settings.telegram_token,), daemon=True).start()
    interval = args.interval_hours or settings.interval_hours
    while True:
        run_once()
        time.sleep(interval * 3600)


if __name__ == "__main__":
    main()
