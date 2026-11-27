from __future__ import annotations

import argparse
import concurrent.futures
import time

from career.matcher import match_job
from career.models import Job


def run_load(users: int = 50, jobs_per_user: int = 100, workers: int = 8) -> dict[str, float | int]:
    if min(users, jobs_per_user, workers) < 1:
        raise ValueError("users, jobs_per_user and workers must be positive")

    jobs = [
        Job(
            title="QA Engineer",
            url=f"https://load.test/job/{index}",
            source="load-test",
            description=(
                "Удалённая работа. Ищем инженера по тестированию. "
                "Требования: manual testing, SQL, Selenium, API testing."
            ),
        )
        for index in range(jobs_per_user)
    ]
    profile = {
        "skills": ["manual testing", "sql", "selenium", "api testing"],
        "skill_groups": {"qa": ["manual testing", "sql", "selenium", "api testing"]},
    }

    def process_user(_: int) -> int:
        return sum(match_job(job, profile).score >= 0.60 for job in jobs)

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        matched = sum(executor.map(process_user, range(users)))
    elapsed = time.perf_counter() - started
    return {
        "users": users,
        "jobs_per_user": jobs_per_user,
        "workers": workers,
        "matches": matched,
        "errors": 0,
        "elapsed_seconds": round(elapsed, 3),
        "matches_per_second": round(matched / max(elapsed, 0.001), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Personal Career matcher load test")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    print(run_load(args.users, args.jobs, args.workers))


if __name__ == "__main__":
    main()
