from autotests.load_scenario import run_load


def test_matcher_handles_parallel_synthetic_burst() -> None:
    result = run_load(users=20, jobs_per_user=50, workers=4)

    assert result["errors"] == 0
    assert result["matches"] == 20 * 50
    assert result["elapsed_seconds"] < 10
