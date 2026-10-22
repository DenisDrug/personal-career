import argparse
import time

from .config import load_settings
from .matcher import match_job
from .resumes import load_profile
from .sources import search_all
from .storage import Storage
from .telegram import send_match


def run_once() -> int:
    settings = load_settings()
    profile = load_profile(settings.resume_dir, settings.extra_skills)
    jobs = search_all(settings.timeout)
    storage = Storage(settings.database_path)
    sent = 0
    for job in jobs:
        if storage.already_sent(job.url):
            continue
        match = match_job(job, profile)
        if match.score < settings.threshold:
            continue
        try:
            send_match(settings.telegram_token, settings.telegram_chat_id, match, settings.timeout)
        except Exception as exc:
            print(f"Telegram notification failed for {job.url}: {exc}")
            continue
        storage.mark_sent(job.url)
        sent += 1
    print(f"Found {len(jobs)} jobs, sent {sent} notifications")
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
    interval = args.interval_hours or settings.interval_hours
    while True:
        run_once()
        time.sleep(interval * 3600)


if __name__ == "__main__":
    main()
