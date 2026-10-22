from urllib.parse import urlencode, urljoin
import re
import time

import httpx
from bs4 import BeautifulSoup

from ..models import Job

QUERIES = ("QA Engineer", "IT Project Manager")


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
            url = urljoin(base_url, link.get("href", ""))
            title = " ".join(title_node.get_text(" ", strip=True).split())
            text = " ".join(card.get_text(" ", strip=True).split())
            if title and url.startswith("http"):
                jobs[url] = Job(title=title[:180], url=url, source=source, description=text[:7000], language=_language_hint(text))

    # Fallback for simpler HTML layouts such as remote-job.ru.
    for link in soup.select("a[href]"):
        title = " ".join(link.get_text(" ", strip=True).split())
        href = urljoin(base_url, link.get("href", ""))
        if not title or len(title) < 5 or not href.startswith("http"):
            continue
        text = " ".join(link.parent.get_text(" ", strip=True).split()) if link.parent else title
        lowered = f"{title} {text}".lower()
        if ("/jobs/" in href or "/vacancy/" in href) and any(
            term in lowered for term in ("qa", "quality", "тест", "project manager", "pm")
        ):
            jobs.setdefault(href, Job(title=title[:180], url=href, source=source, description=text[:7000], language=_language_hint(text)))
    return list(jobs.values())


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
                    description=" ".join(node.get_text(" ", strip=True).split()),
                    location=job.location,
                    company=job.company,
                    language=job.language,
                    skills=job.skills,
                )
            break
        except httpx.HTTPError:
            if attempt == 0:
                time.sleep(0.3)
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
        languages = ", ".join(x.get("name", "") for x in (item.get("languages") or []) if x.get("name"))
        vacancy_url = item.get("alternate_url") or item.get("url", "")
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
        )
        jobs.append(_hh_enrich(client, job))
    return jobs


def search_all(timeout: float) -> list[Job]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    jobs: list[Job] = []
    client_timeout = httpx.Timeout(timeout, connect=min(timeout, 8))
    with httpx.Client(headers=headers, timeout=client_timeout, follow_redirects=True) as client:
        for query in QUERIES:
            sources = {
                "hirify.me": "https://hirify.me/?" + urlencode({"search": query}),
                "talanto.work": "https://talanto.work/?" + urlencode({"q": query}),
                "instahyre.com": "https://www.instahyre.com/search-jobs/",
                "remote-job.ru": "https://remote-job.ru/search?" + urlencode({"search[query]": query}),
            }
            for source, url in sources.items():
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    jobs.extend(_extract(source, url, response.text))
                except httpx.HTTPStatusError as exc:
                    if source == "hh.ru" and exc.response.status_code == 403:
                        try:
                            fallback = client.get(
                                "https://hh.ru/search/vacancy",
                                params={"text": query, "area": 1},
                            )
                            fallback.raise_for_status()
                            jobs.extend(_extract(source, str(fallback.url), fallback.text))
                            continue
                        except httpx.HTTPError as fallback_exc:
                            print(f"[{source}] API and HTML fallback blocked: {fallback_exc}")
                            continue
                    print(f"[{source}] search failed: {exc}")
                except httpx.HTTPError as exc:
                    print(f"[{source}] search failed: {exc}")
            try:
                jobs.extend(_hh_jobs(client, query))
            except (httpx.HTTPError, ValueError) as exc:
                print(f"[hh.ru] API search failed: {exc}")
    return list({job.url: job for job in jobs if job.url}.values())
