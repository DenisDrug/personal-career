import argparse
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import load_settings
from .matcher import match_job
from .resumes import load_profile
from .sources import search_all
from .storage import Storage
from .telegram import send_match


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


def run_once(since: datetime | None = None, chat_id: str | None = None, skip_sent: bool = True, mark_sent: bool = True) -> int:
    settings = load_settings()
    profile = load_profile(settings.resume_dir, settings.extra_skills)
    jobs = search_all(settings.timeout, since=since)
    storage = Storage(settings.database_path)
    russian_jobs = 0
    matched_jobs = 0
    sent = 0
    for job in jobs:
        if skip_sent and storage.already_sent(job.url):
            continue
        if not is_russian_job(job):
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
