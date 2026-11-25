"""Browser-backed Instahyre source.

Instahyre renders the public search page with JavaScript, so a regular HTTP
client only receives the application shell.  This adapter deliberately keeps
the browser session short and serializes it: one search run opens one page,
collects the visible cards, and closes Chromium.
"""

from __future__ import annotations

import threading
from urllib.parse import urljoin

from ..models import Job

_BROWSER_LOCK = threading.Lock()


def _clean(value: str) -> str:
    return " ".join(value.split())


def _job_from_card(card, url: str) -> Job | None:
    title_node = card.locator("h2, h3").first
    title = _clean(title_node.inner_text()) if title_node.count() else ""
    if not title:
        return None

    text = _clean(card.inner_text())
    location = ""
    for candidate in ("Work From Home", "Remote", "Bangalore", "Gurgaon", "Hyderabad", "Delhi"):
        if candidate.lower() in text.lower():
            location = candidate
            break

    company = title.split(" - ", 1)[0].strip() if " - " in title else ""
    return Job(
        title=title[:180],
        url=url,
        source="instahyre.com",
        description=text[:7000],
        location=location,
        company=company,
    )


def search_instahyre(query: str, timeout: float = 20.0, max_jobs: int = 20) -> list[Job]:
    """Search public Instahyre cards in a real browser session.

    Playwright and its Chromium browser are optional.  Importing them inside
    this function lets every other source continue to work when the optional
    browser component is not installed on a server.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed; install the browser extra") from exc

    jobs: dict[str, Job] = {}
    with _BROWSER_LOCK:
        with sync_playwright() as playwright:
            browser = None
            try:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1200},
                    locale="en-US",
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
                    ),
                )
                page.goto(
                    "https://www.instahyre.com/search-jobs/",
                    wait_until="domcontentloaded",
                    timeout=int(timeout * 1000),
                )
                page.wait_for_selector('input[placeholder*="skills or title"]', timeout=int(timeout * 1000))
                search_box = page.locator('input[placeholder*="skills or title"]').first
                search_box.fill(query)
                page.get_by_role("button", name="Search").click()
                page.wait_for_timeout(2500)
                for link in page.locator('a[href*="/job-"]').all()[:max_jobs]:
                    href = link.get_attribute("href") or ""
                    if not href:
                        continue
                    url = urljoin("https://www.instahyre.com/", href).split("?", 1)[0]
                    job = _job_from_card(link, url)
                    if job:
                        jobs[url] = job
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(f"Instahyre browser timeout for query {query!r}") from exc
            except PlaywrightError as exc:
                raise RuntimeError(f"Instahyre browser error for query {query!r}: {exc}") from exc
            finally:
                # Browser processes must be closed even if one card is malformed.
                if browser is not None:
                    browser.close()
    return list(jobs.values())
