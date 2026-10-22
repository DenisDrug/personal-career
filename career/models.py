from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    title: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    company: str = ""
    skills: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Match:
    job: Job
    score: float
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
