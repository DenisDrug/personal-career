from urllib.parse import urlencode, urljoin
import re

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


def _hh_jobs(client: httpx.Client, query: str) -> list[Job]:
    response = client.get(
        "https://api.hh.ru/vacancies",
        params={"text": query, "per_page": 50, "page": 0, "host": "hh.ru", "locale": "RU"},
    )
    response.raise_for_status()
    jobs = []
    for item in response.json().get("items", []):
        snippet = item.get("snippet") or {}
        description = " ".join(filter(None, [snippet.get("requirement"), snippet.get("responsibility")]))
        languages = ", ".join(x.get("name", "") for x in (item.get("languages") or []) if x.get("name"))
        jobs.append(Job(
            title=item.get("name", query),
            url=item.get("alternate_url") or item.get("url", ""),
            source="hh.ru",
            description=description,
            location=(item.get("area") or {}).get("name", ""),
            company=(item.get("employer") or {}).get("name", ""),
            language=languages,
        ))
    return jobs


def search_all(timeout: float) -> list[Job]:
    headers = {"User-Agent": "personal-career/0.1 (+job-search)"}
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
                except httpx.HTTPError as exc:
                    print(f"[{source}] search failed: {exc}")
            try:
                jobs.extend(_hh_jobs(client, query))
            except (httpx.HTTPError, ValueError) as exc:
                print(f"[hh.ru] API search failed: {exc}")
    return list({job.url: job for job in jobs if job.url}.values())
