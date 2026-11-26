import argparse
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import load_settings
from .matcher import match_job, role_for_title
from .resumes import load_profile
from .roles import ROLE_CATALOG
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
    "офис",
    "в офисе",
    "на месте",
    "офисный формат",
    "офисная работа",
)
TECHNICAL_ENGLISH_MARKERS = (
    "api", "sql", "git", "github", "gitlab", "jira", "confluence", "postman", "swagger",
    "selenium", "playwright", "cypress", "allure", "testrail", "browserstack", "devtools",
    "docker", "kubernetes", "python", "java", "javascript", "typescript", "figma", "wordpress",
    "qa", "ui", "ux", "test case", "test plan", "bug report", "documentation",
)
WORKING_ENGLISH_MARKERS = (
    r"\b(?:english|английск(?:ий|ого|ом|им))\b.{0,100}\b(?:b2|c1|c2|upper[- ]?intermediate|intermediate|advanced|fluent|свободн|переговор)",
    r"\b(?:b2|c1|c2|upper[- ]?intermediate|intermediate|advanced|fluent)\b",
    r"\b(?:английский|english)\b.{0,100}(?:переговоры|общение с клиентами|international team|daily communication)",
)


def _has_location_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text) for marker in markers)


def is_work_format_allowed(job, work_format: str = "remote") -> bool:
    """Filter vacancies by the user's preferred work format."""
    location = (job.location or "").lower()
    text = f"{location} {job.title} {job.description}".lower()
    explicit_non_remote = any(marker in text for marker in NON_REMOTE_MARKERS)
    explicit_remote = any(marker in text for marker in REMOTE_MARKERS)
    explicitly_not_remote = bool(
        re.search(
            r"(?:не\s+(?:полностью\s+)?удал[её]нн|без\s+удал[её]нн|"
            r"удал[её]нн(?:ый|ая|ое|ую)?\s+(?:формат\s+)?не\s+(?:предусмотрен|предоставляется)|"
            r"только\s+(?:в\s+)?офис)",
            text,
        )
    )
    if work_format == "office":
        # Office mode includes office, hybrid and mixed-format vacancies.
        return explicit_non_remote or not explicit_remote or explicitly_not_remote
    # Remote mode requires an explicit remote option. Mixed vacancies are
    # allowed when remote work is one of the options, but office/hybrid-only
    # and unspecified vacancies are not.
    if explicitly_not_remote:
        return False
    return explicit_remote


def is_russian_remote_job(job) -> bool:
    """Backward-compatible alias for the remote work-format filter."""
    return is_work_format_allowed(job, "remote")


def _requires_working_english(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in WORKING_ENGLISH_MARKERS)


def _language_counts(text: str, ignore_technical: bool = False) -> tuple[int, int]:
    normalized = text.lower()
    if ignore_technical:
        for marker in TECHNICAL_ENGLISH_MARKERS:
            normalized = re.sub(r"(?<![a-z])" + re.escape(marker) + r"(?![a-z])", " ", normalized)
    return len(re.findall(r"[а-яё]", normalized)), len(re.findall(r"[a-z]", normalized))


def is_job_language_allowed(job, language_mode: str = "ru_tech") -> bool:
    """Filter a vacancy by language while allowing technical English in Russian jobs."""
    if language_mode == "any":
        return True
    language = job.language.lower()
    if language and any(marker in language for marker in ("en", "english", "англ")) and not any(
        marker in language for marker in ("ru", "russian", "рус")
    ):
        return False
    text = f"{job.title} {job.description}".lower()
    cyrillic, latin = _language_counts(text, ignore_technical=language_mode == "ru")
    # A Russian vacancy must contain a meaningful Russian description. Technical
    # terms and documentation words do not disqualify it in ru_tech mode.
    if cyrillic < 40:
        return False
    minimum_ratio = 0.45 if language_mode == "ru" else 0.25
    if cyrillic / max(cyrillic + latin, 1) < minimum_ratio:
        return False
    return not _requires_working_english(text)


def is_russian_job(job) -> bool:
    """Backward-compatible alias for the recommended Russian + tech mode."""
    return is_job_language_allowed(job, "ru_tech")


def run_once(
    since: datetime | None = None,
    chat_id: str | None = None,
    role: str | tuple[str, ...] | None = None,
    skip_sent: bool = True,
    mark_sent: bool = True,
    profile: dict | None = None,
    profiles: dict[str, dict] | None = None,
    threshold: float | None = None,
    user_id: str | None = None,
    cancel_event: threading.Event | None = None,
    language_mode: str = "ru_tech",
    work_format: str = "remote",
) -> int:
    settings = load_settings()
    profile = profile or load_profile(settings.resume_dir, settings.extra_skills)
    effective_threshold = settings.threshold if threshold is None else threshold
    roles = tuple(dict.fromkeys(role)) if isinstance(role, (tuple, list)) else ((role,) if role else ())
    search_roles = roles or (None,)
    jobs_by_url = {}
    for search_role in search_roles:
        for job in search_all(settings.timeout, since=since, role=search_role, debug_logs=settings.source_debug_logs):
            jobs_by_url.setdefault(job.url, job)
    jobs = list(jobs_by_url.values())
    storage = Storage(settings.database_path, settings.database_url)
    russian_jobs = 0
    matched_jobs = 0
    sent = 0
    for job in jobs:
        if sent >= settings.max_notifications_per_run:
            break
        if cancel_event and cancel_event.is_set():
            break
        if skip_sent:
            already_sent = (
                storage.already_sent_for_user(user_id, job.url)
                if user_id
                else storage.already_sent(job.url)
            )
            if already_sent:
                continue
        detected_role = role_for_title(job.title)
        if roles and detected_role not in roles:
            continue
        if not is_job_language_allowed(job, language_mode):
            continue
        if not is_work_format_allowed(job, work_format):
            continue
        russian_jobs += 1
        active_profile = (profiles or {}).get(detected_role) if profiles else profile
        if active_profile is None:
            continue
        match = match_job(job, active_profile)
        if match.score < effective_threshold:
            continue
        matched_jobs += 1
        if cancel_event and cancel_event.is_set():
            break
        try:
            send_match(settings.telegram_token, chat_id or settings.telegram_chat_id, match, settings.timeout)
        except Exception as exc:
            print(f"Telegram notification failed for {job.url}: {exc}")
            continue
        if mark_sent:
            if user_id:
                storage.mark_sent_for_user(user_id, job.url)
            else:
                storage.mark_sent(job.url)
        sent += 1
    if user_id:
        storage.record_search_stats(user_id, len(jobs), matched_jobs, sent)
    print(f"Collected {len(jobs)} jobs, Russian {russian_jobs}, matched {matched_jobs}, sent {sent} notifications")
    return sent


def _next_search_time(now: datetime, search_times: tuple[tuple[int, int], ...]) -> datetime:
    for hour, minute in search_times:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    tomorrow = now + timedelta(days=1)
    hour, minute = search_times[0]
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


def run_scheduled_user_searches(settings) -> int:
    """Run the fixed-time search for users who enabled it in the bot menu."""
    storage = Storage(settings.database_path, settings.database_url)
    sent = 0
    users = storage.list_users()
    for user in users:
        if user["status"] != "approved":
            continue
        user_id = user["telegram_id"]
        preferences = storage.get_preferences(user_id)
        if not preferences["auto_search_enabled"]:
            continue
        roles = tuple(preferences["roles"])
        profiles = {}
        for role in roles:
            profile_record = storage.get_profile_for_role(user_id, role)
            if profile_record:
                profiles[role] = profile_record
        if not profiles:
            print(f"Scheduled search skipped for {user_id}: no resume is uploaded", flush=True)
            continue
        roles = tuple(role for role in roles if role in profiles)
        try:
            user_sent = run_once(
                chat_id=user_id,
                role=roles,
                skip_sent=True,
                mark_sent=True,
                profiles={role: profiles[role]["profile"] for role in roles},
                threshold=preferences["threshold"],
                user_id=user_id,
                language_mode=preferences["language_mode"],
                work_format=preferences["work_format"],
            )
            sent += user_sent
            print(f"Scheduled search for {user_id} ({','.join(roles)}): sent {user_sent}", flush=True)
        except Exception as exc:
            print(f"Scheduled search failed for {user_id}: {exc!r}", flush=True)
    return sent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run one search and exit")
    parser.add_argument("--role", choices=tuple(ROLE_CATALOG), help="role for an explicit one-time search")
    args = parser.parse_args()
    settings = load_settings()
    if args.once:
        if settings.test_mode and not args.role:
            print("TEST_MODE=true: use --role for an explicit one-time local search")
            return
        run_once(role=args.role)
        return
    if settings.test_mode:
        print("TEST_MODE=true: scheduled search disabled")
        if settings.telegram_token:
            from .bot import run_bot

            run_bot(settings.telegram_token)
        return

    if settings.telegram_token:
        from .bot import run_bot

        threading.Thread(target=run_bot, args=(settings.telegram_token,), daemon=True).start()
    while True:
        now = datetime.now(ZoneInfo(settings.timezone_name))
        next_run = _next_search_time(now, settings.search_times)
        while True:
            remaining = (next_run - datetime.now(next_run.tzinfo)).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(60, remaining))
        print(f"Scheduled search started at {next_run.isoformat()}")
        run_scheduled_user_searches(settings)
        # Keep the old environment-based admin schedule working during migration.
        for role in settings.scheduled_roles:
            run_once(role=role)


if __name__ == "__main__":
    main()
