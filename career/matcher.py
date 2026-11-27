import re

from .default_profile import DEFAULT_PROFILE, SKILL_ALIASES
from .models import Job, Match
from .roles import role_for_text


IMPLICIT_SKILLS = {"testing theory", "project management theory"}
REQUIRED_MARKERS = (
    "требован",
    "обязан",
    "необходимо",
    "нужно",
    "must",
    "required",
    "requirements",
    "we expect",
)


def _contains(text: str, phrase: str) -> bool:
    phrase = phrase.lower().strip()
    if not phrase:
        return False
    if re.fullmatch(r"[a-z0-9+#. -]+", phrase):
        return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None
    return phrase in text


def _is_required(text: str, skill: str) -> bool:
    """Return whether a skill is mentioned near a vacancy requirement marker."""
    variants = (skill,) + tuple(SKILL_ALIASES.get(skill, ()))
    for variant in variants:
        for match in re.finditer(re.escape(variant.lower().strip()), text):
            window = text[max(0, match.start() - 180): match.end() + 180]
            if any(marker in window for marker in REQUIRED_MARKERS):
                return True
    return False


def role_for_title(title: str) -> str:
    return role_for_text(title, field="title")


def match_job(job: Job, profile: dict) -> Match:
    role = role_for_title(job.title)
    profile_skills = set(profile.get("skill_groups", {}).get(role, set())) or set(profile.get("skills", ()))
    role_catalog = set(DEFAULT_PROFILE["skills"].get(role, ()))
    # The title selects the role, but cannot contribute skills by itself.
    skill_text = f"{job.description} {job.company} {job.location}".lower()
    matched: list[str] = []
    job_skills: list[str] = []
    required_skills: set[str] = set()
    for skill in role_catalog:
        variants = (skill,) + tuple(SKILL_ALIASES.get(skill, ()))
        if any(_contains(skill_text, variant) for variant in variants):
            job_skills.append(skill)
            if _is_required(skill_text, skill):
                required_skills.add(skill)
            if skill in profile_skills or (skill in IMPLICIT_SKILLS and skill in required_skills):
                matched.append(skill)
    matched = sorted(matched)
    job_skills = sorted(job_skills)
    # Score vacancy coverage, not resume size: extra skills in a resume do not
    # reduce the result. Required skills have a higher weight than nice-to-have
    # skills, while the role title itself contributes zero points.
    total_weight = sum(1.5 if skill in required_skills else 1.0 for skill in job_skills)
    matched_weight = sum(1.5 if skill in required_skills else 1.0 for skill in matched)
    score = matched_weight / total_weight if total_weight else 0.0
    missing = sorted(set(job_skills) - set(matched))
    return Match(job, score, tuple(matched), tuple(missing))
