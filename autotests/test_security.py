from __future__ import annotations

import subprocess
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from career.main import is_work_format_allowed
from career.models import Job
from career.resumes import MAX_DOCX_XML_BYTES, MAX_RESUME_BYTES, extract_resume_text
from career.storage import Storage


def test_sensitive_runtime_files_are_not_tracked() -> None:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    forbidden = (".env", "career.db", "resumes/", ".venv/")
    assert not any(path == ".env" or path.startswith(forbidden[1:]) for path in tracked)


def test_resume_parser_rejects_oversized_input() -> None:
    assert extract_resume_text("resume.pdf", b"x" * (MAX_RESUME_BYTES + 1)) == ""
    assert extract_resume_text("resume.docx", b"x" * (MAX_RESUME_BYTES + 1)) == ""


def test_resume_parser_rejects_oversized_docx_xml() -> None:
    content = BytesIO()
    with ZipFile(content, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * (MAX_DOCX_XML_BYTES + 1))
    assert extract_resume_text("resume.docx", content.getvalue()) == ""


def test_remote_filter_does_not_accept_unspecified_or_office_only_jobs() -> None:
    def job(text: str) -> Job:
        return Job("QA Engineer", "https://test/job", "test", description=text)

    assert is_work_format_allowed(job("Удалённая работа."), "remote")
    assert not is_work_format_allowed(job("Гибридный формат, 3 дня в офисе."), "remote")
    assert not is_work_format_allowed(job("Работа в офисе."), "remote")
    assert not is_work_format_allowed(job("Формат работы не указан."), "remote")


def test_storage_can_be_closed_with_context_manager(tmp_path) -> None:
    with Storage(tmp_path / "career.db") as storage:
        storage.upsert_user("security-test")
        assert storage.get_user("security-test") is not None
