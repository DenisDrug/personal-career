from datetime import datetime

from career.main import _next_search_time, is_job_language_allowed, is_work_format_allowed
from career.models import Job
from career.storage import Storage


def _job(description: str, location: str = "") -> Job:
    return Job(
        title="QA Engineer",
        url="https://example.test/job",
        source="test",
        description=description,
        location=location,
    )


def test_russian_language_filter_allows_technical_english() -> None:
    description = (
        "Ищем инженера по тестированию для работы в команде. "
        "Нужно тестировать API, SQL и работать с Jira. "
        "Документация и тестовые сценарии ведутся в проекте."
    )

    assert is_job_language_allowed(_job(description), "ru_tech")
    assert not is_job_language_allowed(_job("English is required for daily communication with the team." * 3), "ru")


def test_remote_filter_allows_unspecified_and_remote_but_rejects_office_only() -> None:
    assert is_work_format_allowed(_job("Тестирование веб-приложения."), "remote")
    assert is_work_format_allowed(_job("Удалённая работа по договору."), "remote")
    assert not is_work_format_allowed(_job("Работа только в офисе, удалённый формат не предусмотрен."), "remote")


def test_office_filter_allows_office_and_hybrid() -> None:
    assert is_work_format_allowed(_job("Гибридный формат работы: 2 дня в офисе."), "office")
    assert is_work_format_allowed(_job("Работа в офисе."), "office")


def test_next_search_time_uses_configured_timezone_independent_times() -> None:
    now = datetime(2026, 11, 25, 12, 30)

    assert _next_search_time(now, ((8, 0), (12, 0), (15, 0), (18, 0))) == datetime(2026, 11, 25, 15, 0)
    assert _next_search_time(datetime(2026, 11, 25, 19, 0), ((8, 0), (12, 0), (15, 0), (18, 0))) == datetime(2026, 11, 26, 8, 0)


def test_search_stats_are_scoped_to_user_and_deleted_with_user(tmp_path) -> None:
    storage = Storage(tmp_path / "career.db")
    storage.upsert_user("user-1", username="one")
    storage.upsert_user("user-2", username="two")
    storage.record_search_stats("user-1", jobs_collected=10, jobs_matched=3, jobs_sent=2)
    storage.record_search_stats("user-1", jobs_collected=4, jobs_matched=1, jobs_sent=1)
    storage.record_search_stats("user-2", jobs_collected=100, jobs_matched=90, jobs_sent=80)

    assert storage.get_search_stats("user-1")["search_count"] == 2
    assert storage.get_search_stats("user-1")["jobs_sent"] == 3
    assert storage.get_search_stats("user-2")["jobs_sent"] == 80

    assert storage.delete_user("user-1")
    assert storage.get_search_stats("user-1")["search_count"] == 0
    assert storage.get_search_stats("user-2")["search_count"] == 1
