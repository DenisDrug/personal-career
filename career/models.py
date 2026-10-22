from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Job:
    title: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    company: str = ""
    language: str = ""
    skills: set[str] = field(default_factory=set)
    published_at: datetime | None = None


@dataclass(frozen=True)
class Match:
    job: Job
    score: float
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
