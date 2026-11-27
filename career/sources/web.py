from urllib.parse import urlencode, urljoin, urlsplit
from datetime import datetime, timedelta, timezone
import json
import re
import time

import httpx
from bs4 import BeautifulSoup

from ..models import Job
from ..roles import ROLE_CATALOG, ROLE_KEYS
from .instahyre import search_instahyre

ROLE_QUERIES = {key: role["queries"] for key, role in ROLE_CATALOG.items()}
QUERIES = tuple(query for values in ROLE_QUERIES.values() for query in values)


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.netloc.endswith("hh.ru") and parts.path.startswith("/vacancy/"):
        return f"https://hh.ru{parts.path}"
    if parts.netloc.endswith("instahyre.com") and "/job-" in parts.path:
        return f"https://www.instahyre.com{parts.path}"
    return url


def _published_at_from_text(text: str) -> datetime | None:
    lowered = text.lower()
    now = datetime.now(timezone.utc)
    match = re.search(r"(\d+)\s*(минут|минуты|час|часа|часов|дн\.?|день|дня|days?|minute|minutes|hour|hours)\s*(назад|ago)", lowered)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith(("мин", "minute")):
            delta = timedelta(minutes=amount)
        elif unit.startswith(("д", "day")):
            delta = timedelta(days=amount)
        else:
            delta = timedelta(hours=amount)
        return now - delta
    if "сегодня" in lowered or "today" in lowered:
        return now
    months = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    }
    match = re.search(r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b", lowered)
    if match:
        return datetime(now.year, months[match.group(2)], int(match.group(1)), tzinfo=timezone.utc)
    return None


def _language_hint(text: str) -> str:
    lowered = text.lower()
    if re.search(r"(?:язык|language|vacancy language)\s*[:：-]?\s*(?:en|english|англ)", lowered):
        return "en"
    if re.search(r"(?:язык|language|vacancy language)\s*[:：-]?\s*(?:ru|рус|russian|русский)", lowered):
        return "ru"
    return ""


def _extract(source: str, base_url: str, html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, Job] = {}
    for card in soup.select("article.vacancy-card"):
        link = card.select_one('a[href*="/jobs/"]')
        title_node = card.select_one("h3, h2")
        if link and title_node:
            url = _canonical_url(urljoin(base_url, link.get("href", "")))
            title = " ".join(title_node.get_text(" ", strip=True).split())
            text = " ".join(card.get_text(" ", strip=True).split())
            if title and url.startswith("http"):
                jobs[url] = Job(title=title[:180], url=url, source=source, description=text[:7000], language=_language_hint(text), published_at=_published_at_from_text(text))

    # Fallback for simpler HTML layouts such as remote-job.ru.
    for link in soup.select("a[href]"):
        title = " ".join(link.get_text(" ", strip=True).split())
        href = _canonical_url(urljoin(base_url, link.get("href", "")))
        if not title or len(title) < 5 or not href.startswith("http"):
            continue
        text = " ".join(link.parent.get_text(" ", strip=True).split()) if link.parent else title
        lowered = f"{title} {text}".lower()
        role_markers = tuple(
            term.lower()
            for role in ROLE_CATALOG.values()
            for term in role["title_terms"]
        )
        if ("/jobs/" in href or "/vacancy/" in href) and any(term in lowered for term in role_markers):
            jobs.setdefault(href, Job(title=title[:180], url=href, source=source, description=text[:7000], language=_language_hint(text), published_at=_published_at_from_text(text)))
    return list(jobs.values())


def _extract_habr(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, Job] = {}
    for card in soup.select(".vacancy-card"):
        link = card.select_one(".vacancy-card__title-link, .vacancy-card__backdrop-link")
        title_node = card.select_one(".vacancy-card__title-link")
        if not link or not title_node:
            continue
        url = urljoin("https://career.habr.com/", link.get("href", ""))
        title = " ".join(title_node.get_text(" ", strip=True).split())
        if not title or not url.startswith("https://career.habr.com/vacancies/"):
            continue
        meta = [
            " ".join(node.get_text(" ", strip=True).split())
            for node in card.select(".vacancy-card__meta .chip-with-icon__text")
        ]
        location = ", ".join(value for value in meta if "удалён" not in value.lower() and "удален" not in value.lower())
        text = " ".join(card.get_text(" ", strip=True).split())
        published_at = None
        date_node = card.select_one("time[datetime]")
        if date_node and date_node.get("datetime"):
            published_at = datetime.fromisoformat(date_node["datetime"])
        jobs[url] = Job(
            title=title[:180],
            url=url,
            source="career.habr.com",
            description=text[:7000],
            location=location,
            company=" ".join(card.select_one(".vacancy-card__company").get_text(" ", strip=True).split())
            if card.select_one(".vacancy-card__company")
            else "",
            published_at=published_at,
        )
    return list(jobs.values())


def _habr_enrich(client: httpx.Client, job: Job) -> Job:
    """Load Habr Career's full vacancy description and structured metadata."""
    try:
        page = client.get(job.url)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        state_node = soup.select_one('script[type="application/json"][data-ssr-state]')
        state = json.loads(state_node.get_text()) if state_node else {}
        vacancy = state.get("vacancy") or {}
        description_html = vacancy.get("description") or ""
        description = " ".join(BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True).split())
        remote_work = vacancy.get("remoteWork") is True
        if remote_work:
            description = f"{description} Можно удалённо".strip()
        location_data = vacancy.get("location") or {}
        location = location_data.get("title", "") if isinstance(location_data, dict) else str(location_data)
        published_at = job.published_at
        published_date = (vacancy.get("publishedDate") or {}).get("date")
        if published_date:
            published_at = datetime.fromisoformat(published_date)
        return Job(
            title=vacancy.get("title") or job.title,
            url=job.url,
            source=job.source,
            description=description or job.description,
            location=location or job.location,
            company=(vacancy.get("company") or {}).get("title", "") or job.company,
            language=job.language,
            skills=job.skills,
            published_at=published_at,
        )
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return job


def _habr_jobs(client: httpx.Client, query: str) -> list[Job]:
    response = client.get("https://career.habr.com/vacancies", params={"q": query})
    response.raise_for_status()
    return [_habr_enrich(client, job) for job in _extract_habr(response.text)]


def _hh_enrich(client: httpx.Client, job: Job) -> Job:
    """Replace HH's search snippet with the full public vacancy description."""
    if not job.url:
        return job
    for attempt in range(2):
        try:
            time.sleep(0.8 if attempt == 0 else 1.5)
            page = httpx.get(
                job.url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                },
                timeout=client.timeout,
                follow_redirects=True,
            )
            page.raise_for_status()
            node = BeautifulSoup(page.text, "html.parser").select_one('[data-qa="vacancy-description"]')
            if node:
                return Job(
                    title=job.title,
                    url=job.url,
                    source=job.source,
                    description=f"{job.description} {' '.join(node.get_text(' ', strip=True).split())}".strip(),
                    location=job.location,
                    company=job.company,
                    language=job.language,
                    skills=job.skills,
                    published_at=job.published_at,
                )
            break
        except httpx.HTTPError:
            if attempt == 0:
                time.sleep(0.3)
    return job


def _hirify_enrich(client: httpx.Client, job: Job) -> Job:
    """Load Hirify's full description instead of the short listing card."""
    try:
        page = client.get(job.url)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        heading = soup.find(lambda tag: tag.name in ("h2", "h3") and "Описание вакансии" in tag.get_text(" ", strip=True))
        island = heading.find_parent(class_="island") if heading else None
        if island:
            description = " ".join(island.get_text(" ", strip=True).split())
            return Job(
                title=job.title,
                url=job.url,
                source=job.source,
                description=description,
                location=job.location,
                company=job.company,
                language=job.language,
                skills=job.skills,
                published_at=job.published_at,
            )
    except httpx.HTTPError:
        pass
    return job


def _remote_job_enrich(client: httpx.Client, job: Job) -> Job:
    """Load Remote Job's full vacancy description instead of a listing snippet."""
    try:
        page = client.get(job.url)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        heading = soup.find(lambda tag: tag.name in ("h2", "h3") and "Описание вакансии" in tag.get_text(" ", strip=True))
        panel = heading.find_parent(class_="panel-body") if heading else None
        if panel:
            return Job(
                title=job.title,
                url=job.url,
                source=job.source,
                description=" ".join(panel.get_text(" ", strip=True).split()),
                location=job.location,
                company=job.company,
                language=job.language,
                skills=job.skills,
                published_at=job.published_at,
            )
    except httpx.HTTPError:
        pass
    return job


def _talanto_enrich(client: httpx.Client, job: Job) -> Job:
    """Load Talanto's article body instead of the short listing card."""
    try:
        page = client.get(job.url)
        page.raise_for_status()
        node = BeautifulSoup(page.text, "html.parser").select_one(".article-body")
        if node:
            return Job(
                title=job.title,
                url=job.url,
                source=job.source,
                description=" ".join(node.get_text(" ", strip=True).split()),
                location=job.location,
                company=job.company,
                language=job.language,
                skills=job.skills,
                published_at=job.published_at,
            )
    except httpx.HTTPError:
        pass
    return job


def _hh_jobs(client: httpx.Client, query: str) -> list[Job]:
    try:
        response = client.get(
            "https://api.hh.ru/vacancies",
            params={"text": query, "per_page": 50, "page": 0, "host": "hh.ru", "locale": "RU"},
            headers={
                "Accept": "application/json",
                "HH-User-Agent": "personal-career/1.0 (https://github.com/DenisDrug/personal-career)",
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        fallback = client.get("https://hh.ru/search/vacancy", params={"text": query, "area": 1})
        fallback.raise_for_status()
        return [_hh_enrich(client, job) for job in _extract("hh.ru", str(fallback.url), fallback.text)]
    jobs = []
    for item in response.json().get("items", []):
        snippet = item.get("snippet") or {}
        description = " ".join(filter(None, [snippet.get("requirement"), snippet.get("responsibility")]))
        schedule = item.get("schedule") or {}
        work_formats = item.get("work_format") or []
        format_hints = [schedule.get("name", ""), schedule.get("id", "")]
        format_hints.extend(
            value.get("name", "") if isinstance(value, dict) else str(value)
            for value in work_formats
        )
        format_hints = list(dict.fromkeys(value for value in format_hints if value))
        if format_hints:
            description = f"Формат работы: {', '.join(format_hints)}. {description}".strip()
        languages = ", ".join(x.get("name", "") for x in (item.get("languages") or []) if x.get("name"))
        published_at = None
        if item.get("published_at"):
            published_at = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        vacancy_url = _canonical_url(item.get("alternate_url") or item.get("url", ""))
        # HH search results contain only a short snippet. Fetch the public page
        # so matching sees the complete requirements and responsibilities.
        job = Job(
            title=item.get("name", query),
            url=vacancy_url,
            source="hh.ru",
            description=description,
            location=(item.get("area") or {}).get("name", ""),
            company=(item.get("employer") or {}).get("name", ""),
            language=languages,
            published_at=published_at,
        )
        jobs.append(_hh_enrich(client, job))
    return jobs


def search_all(
    timeout: float,
    since: datetime | None = None,
    role: str | None = None,
    debug_logs: bool = False,
) -> list[Job]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    jobs: list[Job] = []
    source_names = ("hirify.me", "talanto.work", "instahyre.com", "remote-job.ru", "career.habr.com", "hh.ru")
    source_stats = {
        source: {"requests": 0, "found": 0, "errors": 0, "statuses": {}}
        for source in source_names
    }

    def record_status(source: str, status: str) -> None:
        statuses = source_stats[source]["statuses"]
        statuses[status] = statuses.get(status, 0) + 1

    def log_source_result(source: str, query: str, found: int) -> None:
        stats = source_stats[source]
        stats["found"] += found
        if debug_logs:
            print(
                f"[{source}] query={query!r} requests={stats['requests']} "
                f"found={found} errors={stats['errors']}",
                flush=True,
            )

    client_timeout = httpx.Timeout(timeout, connect=min(timeout, 8))
    role_keys = (role,) if role in ROLE_CATALOG else ROLE_KEYS
    query_groups = [(role_key, query) for role_key in role_keys for query in ROLE_QUERIES[role_key]]
    with httpx.Client(headers=headers, timeout=client_timeout, follow_redirects=True) as client:
        for role_key, query in query_groups:
            sources = {
                "hirify.me": "https://hirify.me/?" + urlencode({"search": query}),
                "talanto.work": "https://talanto.work/?" + urlencode({"q": query}),
                "instahyre.com": "https://www.instahyre.com/search-jobs/",
                "remote-job.ru": "https://remote-job.ru/search?" + urlencode({
                    "search[query]": ROLE_CATALOG[role_key]["remote_query"]
                }),
            }
            for source, url in sources.items():
                if source == "instahyre.com" and query != ROLE_QUERIES[role_key][0]:
                    # The public Instahyre endpoint has no query parameter;
                    # avoid making the same blocked request for every synonym.
                    continue
                source_stats[source]["requests"] += 1
                try:
                    if source == "instahyre.com":
                        extracted = search_instahyre(query, timeout=timeout)
                        jobs.extend(extracted)
                        record_status(source, "browser:200")
                        log_source_result(source, query, len(extracted))
                        continue
                    response = client.get(url)
                    response.raise_for_status()
                    record_status(source, str(response.status_code))
                    if source == "hirify.me" and "Too many requests" in response.text:
                        source_stats[source]["errors"] += 1
                        record_status(source, "429_embedded")
                        print(
                            "[hirify.me] search blocked by anti-bot protection; official API access is required",
                            flush=True,
                        )
                        continue
                    if source == "instahyre.com" and "enable JavaScript" in response.text:
                        source_stats[source]["errors"] += 1
                        record_status(source, "javascript_shell")
                        print(
                            "[instahyre.com] search returned JavaScript shell; browser/API integration is required",
                            flush=True,
                        )
                        continue
                    extracted = _extract(source, url, response.text)
                    if source == "hirify.me":
                        extracted = [_hirify_enrich(client, job) for job in extracted]
                    elif source == "remote-job.ru":
                        extracted = [_remote_job_enrich(client, job) for job in extracted]
                    elif source == "talanto.work":
                        extracted = [_talanto_enrich(client, job) for job in extracted]
                    jobs.extend(extracted)
                    log_source_result(source, query, len(extracted))
                except httpx.HTTPStatusError as exc:
                    source_stats[source]["errors"] += 1
                    record_status(source, str(exc.response.status_code))
                    if source == "hh.ru" and exc.response.status_code == 403:
                        try:
                            fallback = client.get(
                                "https://hh.ru/search/vacancy",
                                params={"text": query, "area": 1},
                            )
                            fallback.raise_for_status()
                            record_status(source, f"fallback:{fallback.status_code}")
                            fallback_jobs = _extract(source, str(fallback.url), fallback.text)
                            jobs.extend(fallback_jobs)
                            log_source_result(source, query, len(fallback_jobs))
                            continue
                        except httpx.HTTPError as fallback_exc:
                            print(f"[{source}] API and HTML fallback blocked: {fallback_exc}")
                            continue
                    print(f"[{source}] search failed: {exc}")
                except RuntimeError as exc:
                    source_stats[source]["errors"] += 1
                    record_status(source, type(exc).__name__)
                    print(f"[{source}] browser search skipped: {exc}", flush=True)
                except httpx.HTTPError as exc:
                    source_stats[source]["errors"] += 1
                    record_status(source, type(exc).__name__)
                    print(f"[{source}] search failed: {exc}")
            try:
                source_stats["career.habr.com"]["requests"] += 1
                habr_jobs = _habr_jobs(client, query)
                jobs.extend(habr_jobs)
                record_status("career.habr.com", "200")
                log_source_result("career.habr.com", query, len(habr_jobs))
            except (httpx.HTTPError, ValueError) as exc:
                source_stats["career.habr.com"]["errors"] += 1
                record_status("career.habr.com", type(exc).__name__)
                print(f"[career.habr.com] search failed: {exc}")
            try:
                source_stats["hh.ru"]["requests"] += 1
                hh_jobs = _hh_jobs(client, query)
                jobs.extend(hh_jobs)
                record_status("hh.ru", "200_or_fallback")
                log_source_result("hh.ru", query, len(hh_jobs))
            except (httpx.HTTPError, ValueError) as exc:
                source_stats["hh.ru"]["errors"] += 1
                record_status("hh.ru", type(exc).__name__)
                print(f"[hh.ru] API search failed: {exc}")
    unique_jobs = list({job.url: job for job in jobs if job.url}.values())
    if since is not None:
        unique_jobs = [job for job in unique_jobs if job.published_at and job.published_at >= since]
    print("Search source statistics:", flush=True)
    for source, stats in source_stats.items():
        statuses = ", ".join(f"{status}={count}" for status, count in stats["statuses"].items()) or "none"
        print(
            f"  [{source}] requests={stats['requests']} found={stats['found']} "
            f"errors={stats['errors']} statuses={statuses}",
            flush=True,
        )
    return unique_jobs
