import re

from .models import Job, Match


def _terms(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zа-яё][a-zа-яё0-9+.#-]{1,}", text.lower())}


def match_job(job: Job, profile: dict) -> Match:
    text = f"{job.title} {job.description} {job.company} {job.location}".lower()
    matched = sorted(skill for skill in profile["skills"] if skill.lower() in text)
    # Score is skill coverage, with a small title relevance bonus capped at 1.
    score = len(matched) / max(len(profile["skills"]), 1)
    role_hit = any(role in text for role in profile.get("roles", []))
    if role_hit:
        score = min(1.0, score + 0.05)
    missing = sorted(profile["skills"] - set(matched))
    return Match(job, score, tuple(matched), tuple(missing))
