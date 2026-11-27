from career.matcher import match_job
from career.models import Job


def _job(description: str) -> Job:
    return Job(
        title="QA Engineer",
        url="https://example.test/job",
        source="test",
        description=description,
    )


def test_score_uses_vacancy_skills_not_resume_size() -> None:
    profile = {"skills": ["manual testing", "sql", "selenium"], "skill_groups": {"qa": ["sql"]}}
    match = match_job(_job("Требования: SQL."), profile)

    assert match.score == 1.0
    assert match.matched_skills == ("sql",)


def test_missing_optional_skill_reduces_score() -> None:
    profile = {
        "skills": ["manual testing", "sql", "selenium"],
        "skill_groups": {"qa": ["manual testing", "sql", "selenium"]},
    }
    match = match_job(_job("Требования: manual testing, SQL. Будет плюсом Allure."), profile)

    assert match.score == 2 / 3
    assert match.missing_skills == ("allure",)


def test_role_title_does_not_add_points_without_skills() -> None:
    profile = {"skills": ["manual testing"], "skill_groups": {"qa": ["manual testing"]}}

    assert match_job(_job("Интересная работа в команде."), profile).score == 0.0


def test_testing_theory_is_implicit_when_required() -> None:
    profile = {"skills": ["sql"], "skill_groups": {"qa": ["sql"]}}
    match = match_job(_job("Требования: теория тестирования и SQL."), profile)

    assert match.score == 1.0
    assert "testing theory" in match.matched_skills
