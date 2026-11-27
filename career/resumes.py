from pathlib import Path
import re

from .default_profile import DEFAULT_PROFILE, SKILL_ALIASES


def _contains(text: str, phrase: str) -> bool:
    phrase = phrase.lower().strip()
    if re.fullmatch(r"[a-z0-9+#. -]+", phrase):
        return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None
    return phrase in text


def _text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception:
        return ""


def load_profile(resume_dir: Path, extra_skills: tuple[str, ...] = ()) -> dict:
    texts = [_text_from_pdf(p) for p in sorted(resume_dir.glob("*.pdf"))]
    corpus = "\n".join(texts).lower()
    profile = {"roles": list(DEFAULT_PROFILE["roles"]), "skills": set(extra_skills), "skill_groups": {}}
    for name, group in DEFAULT_PROFILE["skills"].items():
        found = {
            skill for skill in group
            if any(_contains(corpus, variant) for variant in (skill,) + tuple(SKILL_ALIASES.get(skill, ())))
        }
        profile["skill_groups"][name] = found or set(group)
        profile["skills"].update(profile["skill_groups"][name])
    profile["skills"].update(extra_skills)
    return profile
