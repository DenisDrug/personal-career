import re

from .default_profile import DEFAULT_PROFILE, SKILL_ALIASES
from .models import Job, Match


IMPLICIT_SKILLS = {"testing theory", "project management theory"}


def _contains(text: str, phrase: str) -> bool:
    phrase = phrase.lower().strip()
    if not phrase:
        return False
    if re.fullmatch(r"[a-z0-9+#. -]+", phrase):
        return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None
    return phrase in text


def _role_for_title(title: str) -> str:
    title = title.lower()
    if any(term in title for term in ("qa", "quality assurance", "тестировщик", "tester")):
        return "qa"
    if any(term in title for term in ("project manager", "project management", "менеджер проектов")):
        return "pm"
    return ""


def match_job(job: Job, profile: dict) -> Match:
    text = f"{job.title} {job.description} {job.company} {job.location}".lower()
    role = _role_for_title(job.title)
    skills = set(profile.get("skill_groups", {}).get(role, set())) or set(profile["skills"])
    role_catalog = set(DEFAULT_PROFILE["skills"].get(role, skills))
    # The title selects QA/PM, but cannot contribute skills by itself.
    skill_text = f"{job.description} {job.company} {job.location}".lower()
    matched = []
    job_skills = []
    for skill in role_catalog:
        variants = (skill,) + tuple(SKILL_ALIASES.get(skill, ()))
        if any(_contains(skill_text, variant) for variant in variants):
            job_skills.append(skill)
            if skill in skills or skill in IMPLICIT_SKILLS:
                matched.append(skill)
    matched = sorted(matched)
    job_skills = sorted(job_skills)
    skill_score = len(matched) / max(5, len(job_skills))
    score = min(1.0, skill_score)
    missing = sorted(set(job_skills) - set(matched))
    return Match(job, score, tuple(matched), tuple(missing))
