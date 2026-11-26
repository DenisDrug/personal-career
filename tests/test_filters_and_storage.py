from datetime import datetime
from types import SimpleNamespace

import career.main as main_module
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


def test_remote_filter_requires_remote_and_allows_mixed_remote_options() -> None:
    assert not is_work_format_allowed(_job("Тестирование веб-приложения."), "remote")
    assert is_work_format_allowed(_job("Удалённая работа по договору."), "remote")
    assert is_work_format_allowed(_job("Гибридный формат, возможна удалённая работа."), "remote")
    assert not is_work_format_allowed(_job("Гибридный формат работы: 2 дня в офисе."), "remote")
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


def test_preferences_keep_multiple_roles_and_resume_profiles_are_role_specific(tmp_path) -> None:
    storage = Storage(tmp_path / "career.db")
    storage.upsert_user("user-1", username="one")
    storage.save_preferences("user-1", ("qa", "pm"), 0.6)
    storage.save_profile("user-1", "qa.pdf", "qa-file", {"roles": ["qa"]}, profile_key="qa")
    storage.save_profile("user-1", "pm.pdf", "pm-file", {"roles": ["pm"]}, profile_key="pm")

    assert storage.get_preferences("user-1")["roles"] == ("qa", "pm")
    assert {item["profile_key"] for item in storage.list_profiles("user-1")} == {"qa", "pm"}
    assert storage.get_profile_for_role("user-1", "qa")["filename"] == "qa.pdf"
    assert storage.get_profile_for_role("user-1", "pm")["filename"] == "pm.pdf"


def test_multi_role_search_uses_each_role_profile_and_deduplicates(monkeypatch, tmp_path) -> None:
    jobs = [
        _job("Удалённая работа. Ищем QA инженера. Требования: SQL и ручное тестирование."),
        Job(
            title="Project Manager",
            url="https://example.test/pm",
            source="test",
            description="Удалённая работа. Ищем менеджера проектов. Требования: Agile и управление проектами. " * 2,
        ),
    ]
    jobs[0] = Job(
        title="QA Engineer",
        url="https://example.test/qa",
        source="test",
        description="Удалённая работа. Ищем QA инженера. Требования: SQL и ручное тестирование. " * 2,
    )
    calls = []

    def fake_search_all(timeout, since=None, role=None, debug_logs=False):
        calls.append(role)
        return jobs + [jobs[0]]

    settings = SimpleNamespace(
        timeout=1,
        source_debug_logs=False,
        database_path=tmp_path / "career.db",
        database_url="",
        max_notifications_per_run=10,
        telegram_token="",
        telegram_chat_id="",
        threshold=0.5,
    )
    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "search_all", fake_search_all)
    monkeypatch.setattr(main_module, "send_match", lambda *args, **kwargs: None)

    sent = main_module.run_once(
        role=("qa", "pm"),
        profile={"skills": []},
        profiles={
            "qa": {"skills": ["sql", "manual testing"], "skill_groups": {"qa": ["sql", "manual testing"]}},
            "pm": {"skills": ["agile", "project management"], "skill_groups": {"pm": ["agile", "project management"]}},
        },
        user_id="user-1",
    )

    assert calls == ["qa", "pm"]
    assert sent == 2
