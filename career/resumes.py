from pathlib import Path
import re

from .default_profile import DEFAULT_PROFILE


def _text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception:
        return ""


def load_profile(resume_dir: Path, extra_skills: tuple[str, ...] = ()) -> dict:
    texts = [_text_from_pdf(p) for p in sorted(resume_dir.glob("*.pdf"))]
    corpus = "\n".join(texts).lower()
    profile = {"roles": list(DEFAULT_PROFILE["roles"]), "skills": set(extra_skills)}
    for group in DEFAULT_PROFILE["skills"].values():
        profile["skills"].update(group)
    # Keep only terms that are present when extraction works; fallback profile is retained for scans.
    if corpus.strip():
        found = {skill for skill in profile["skills"] if re.search(r"\b" + re.escape(skill) + r"\b", corpus)}
        if found:
            profile["skills"] = found | set(extra_skills)
    return profile
