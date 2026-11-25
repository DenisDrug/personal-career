from datetime import datetime, timezone

import httpx

from career.models import Job
from career.sources import web


class FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200, payload: dict | None = None):
        self.text = text
        self.status_code = status_code
        self._payload = payload
        self.url = "https://example.test/search"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", self.url),
                response=httpx.Response(self.status_code, request=httpx.Request("GET", self.url)),
            )

    def json(self) -> dict:
        return self._payload or {}


class FakeClient:
    def __init__(self, responses: dict[str, FakeResponse | Exception]):
        self.responses = responses
        self.calls: list[str] = []
        self.timeout = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        for marker, result in self.responses.items():
            if marker in url:
                if isinstance(result, Exception):
                    raise result
                return result
        return FakeResponse("<html></html>")


def test_generic_source_parser_deduplicates_jobs_and_normalizes_hh_url() -> None:
    html = """
    <article class="vacancy-card">
      <h3>QA Engineer</h3>
      <a href="https://hh.ru/vacancy/123?from=search">Открыть</a>
      <p>Требования: SQL, тестирование</p>
    </article>
    <article class="vacancy-card">
      <h3>QA Engineer</h3>
      <a href="https://hh.ru/vacancy/123?query=qa">Дубликат</a>
      <p>Требования: SQL, тестирование</p>
    </article>
    """

    jobs = web._extract("hh.ru", "https://hh.ru/search/vacancy", html)

    assert len(jobs) == 1
    assert jobs[0].url == "https://hh.ru/vacancy/123"


def test_habr_parser_extracts_structured_card() -> None:
    html = """
    <article class="vacancy-card">
      <a class="vacancy-card__title-link" href="/vacancies/123">QA Engineer</a>
      <span class="vacancy-card__company">Example</span>
      <span class="chip-with-icon__text">Москва</span>
      <time datetime="2026-11-24T10:00:00+00:00"></time>
    </article>
    """

    jobs = web._extract_habr(html)

    assert len(jobs) == 1
    assert jobs[0].source == "career.habr.com"
    assert jobs[0].company == "Example"
    assert jobs[0].published_at == datetime(2026, 11, 24, 10, tzinfo=timezone.utc)


def test_hh_api_parser_maps_metadata() -> None:
    client = FakeClient({
        "api.hh.ru": FakeResponse(payload={
            "items": [{
                "name": "QA Engineer",
                "alternate_url": "https://hh.ru/vacancy/456?from=api",
                "snippet": {"requirement": "SQL", "responsibility": "Тестировать"},
                "area": {"name": "Москва"},
                "employer": {"name": "Example"},
                "languages": [{"name": "Русский"}],
                "published_at": "2026-11-24T10:00:00+00:00",
            }]
        })
    })
    # Enrichment uses a direct HTTP call in the current adapter; keep this
    # parser test fully offline.
    original_get = web.httpx.get
    web.httpx.get = lambda *args, **kwargs: FakeResponse("<html></html>")
    try:
        jobs = web._hh_jobs(client, "QA Engineer")
    finally:
        web.httpx.get = original_get

    assert len(jobs) == 1
    assert jobs[0].url == "https://hh.ru/vacancy/456"
    assert jobs[0].company == "Example"
    assert "SQL" in jobs[0].description


def test_search_all_isolates_source_failures(monkeypatch, capsys) -> None:
    talanto_html = """
    <article class="vacancy-card">
      <h3>QA Engineer</h3>
      <a href="/jobs/qa-1">Открыть</a>
      <p>Требования: тестирование и SQL</p>
    </article>
    """
    client = FakeClient({
        "hirify.me": httpx.ReadTimeout("hirify timeout"),
        "talanto.work": FakeResponse(talanto_html),
        "remote-job.ru": httpx.ReadTimeout("remote timeout"),
    })

    monkeypatch.setattr(web.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(web, "search_instahyre", lambda query, timeout: [])
    monkeypatch.setattr(
        web,
        "_habr_jobs",
        lambda client, query: [Job("Habr QA", "https://career.habr.com/vacancies/1", "career.habr.com")],
    )
    monkeypatch.setattr(
        web,
        "_hh_jobs",
        lambda client, query: [Job("HH QA", "https://hh.ru/vacancy/1", "hh.ru")],
    )

    jobs = web.search_all(timeout=1, role="qa", debug_logs=True)
    output = capsys.readouterr().out

    sources = {job.source for job in jobs}
    assert "talanto.work" in sources
    assert "career.habr.com" in sources
    assert "hh.ru" in sources
    assert "[hirify.me] search failed" in output
    assert "[remote-job.ru] search failed" in output
    assert "Search source statistics:" in output


def test_instahyre_browser_error_isolated(monkeypatch, capsys) -> None:
    client = FakeClient({"hirify.me": FakeResponse("<html></html>")})
    monkeypatch.setattr(web.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(
        web,
        "search_instahyre",
        lambda query, timeout: (_ for _ in ()).throw(RuntimeError("browser unavailable")),
    )
    monkeypatch.setattr(web, "_habr_jobs", lambda client, query: [])
    monkeypatch.setattr(web, "_hh_jobs", lambda client, query: [])

    web.search_all(timeout=1, role="qa", debug_logs=True)
    output = capsys.readouterr().out

    assert "[instahyre.com] browser search skipped" in output
