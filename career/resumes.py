from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree

from .default_profile import DEFAULT_PROFILE, SKILL_ALIASES
from .roles import ROLE_CATALOG, ROLE_KEYS, normalize_role_text, role_matches_text


MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_DOCX_XML_BYTES = 5 * 1024 * 1024


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


def extract_resume_text(filename: str, content: bytes) -> str:
    """Extract text in memory; the original uploaded file is not persisted."""
    if len(content) > MAX_RESUME_BYTES:
        return ""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        except Exception:
            return ""
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > MAX_DOCX_XML_BYTES:
                    return ""
                xml = archive.read(info)
            root = ElementTree.fromstring(xml)
            return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
        except Exception:
            return ""
    return ""


def detect_english_level(text: str) -> str:
    lowered = text.lower()
    for level in ("c2", "c1", "b2", "b1", "a2", "a1"):
        if re.search(rf"\b{level}\b", lowered):
            return level.upper()
    if re.search(r"(?:английский|english).{0,80}(?:свободн|fluent|advanced|профессионал)", lowered, re.DOTALL):
        return "C1+"
    if re.search(r"(?:английский|english).{0,80}(?:средн|intermediate)", lowered, re.DOTALL):
        return "B1/B2"
    if re.search(r"(?:английский|english).{0,80}(?:базов|basic|elementary)", lowered, re.DOTALL):
        return "A1/A2"
    return "не указан"


def profile_from_text(text: str, extra_skills: tuple[str, ...] = ()) -> dict:
    corpus = text.lower()
    skill_groups: dict[str, set[str]] = {}
    skills: set[str] = set(extra_skills)
    for name, group in DEFAULT_PROFILE["skills"].items():
        found = {
            skill
            for skill in group
            if any(_contains(corpus, variant) for variant in (skill,) + tuple(SKILL_ALIASES.get(skill, ())))
        }
        skill_groups[name] = found
        skills.update(found)

    # A resume can contain several roles, so check every catalog entry.
    normalized = normalize_role_text(corpus)
    roles = [
        key for key, role in ROLE_CATALOG.items()
        if role_matches_text(normalized, key, field="resume", already_normalized=True)
    ]
    return {
        "roles": roles,
        "skills": sorted(skills),
        "skill_groups": {role: sorted(values) for role, values in skill_groups.items()},
        "source_text_length": len(text),
        "english_level": detect_english_level(text),
    }


def load_profile(resume_dir: Path, extra_skills: tuple[str, ...] = ()) -> dict:
    texts = [_text_from_pdf(p) for p in sorted(resume_dir.glob("*.pdf"))]
    profile = profile_from_text("\n".join(texts), extra_skills)
    if not profile["roles"]:
        profile["roles"] = list(ROLE_KEYS)
    return profile
