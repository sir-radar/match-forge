"""Report GitHub Actions CI timings without downloading logs or test artifacts."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from typing import NamedTuple, TypedDict, cast


class Run(TypedDict):
    id: int
    run_attempt: int
    run_started_at: str
    conclusion: str


class Step(TypedDict):
    name: str
    conclusion: str
    started_at: str | None
    completed_at: str | None


class Job(Step):
    run_attempt: int
    created_at: str | None
    steps: list[Step]


class Timings(NamedTuple):
    seconds: float
    budget: tuple[int, int] | None = None


# Advisory median and p95 thresholds in seconds. See docs/ci.md.
WORKFLOW_BUDGET = (900, 1140)
STEP_BUDGETS = {
    "Check format, lint, architecture and project status": (90, 150),
    "Run Python unit tests and enforce coverage": (420, 540),
    "Run Rust, Go and frontend unit tests": (40, 90),
    "Build Python, Rust, Go and frontend": (60, 100),
    "Install Playwright system packages": (90, 180),
    "Install Playwright browsers": (25, 60),
    "Run isolated database integration and live browser checks": (600, 720),
    "Run standalone browser and accessibility checks": (95, 130),
}


def github(path: str) -> dict[str, object]:
    result = subprocess.run(
        ["gh", "api", path], check=True, stdout=subprocess.PIPE, text=True, timeout=30
    )
    return cast(dict[str, object], json.loads(result.stdout))


def elapsed(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    return seconds if seconds >= 0 else None


def record_run(run: Run, jobs: list[Job], metrics: dict[str, list[Timings]]) -> None:
    current = [job for job in jobs if job["run_attempt"] == run["run_attempt"]]
    if run["conclusion"] != "success":
        return
    for job in current:
        for step in job["steps"]:
            seconds = elapsed(step["started_at"], step["completed_at"])
            if step["conclusion"] == "success" and seconds is not None:
                label = f"Step: {job['name']} / {step['name']}"
                budget = STEP_BUDGETS.get(step["name"])
                # The old Install Playwright browsers step also installed apt packages.
                if job["name"] == "Deterministic checks":
                    budget = None
                metrics[label].append(Timings(seconds, budget))
        seconds = elapsed(job["started_at"], job["completed_at"])
        if job["conclusion"] == "success" and seconds is not None:
            metrics[f"Job: {job['name']}"].append(Timings(seconds))
    record_full_run(run, current, metrics)


def record_full_run(run: Run, jobs: list[Job], metrics: dict[str, list[Timings]]) -> None:
    build_jobs = {"Build, integration and browser checks", "Build and static checks"}
    if not any(job["name"] in build_jobs and job["conclusion"] == "success" for job in jobs):
        return
    # Exclude selective and full reruns from latency budgets; track reruns separately.
    if run["run_attempt"] != 1:
        return
    executed = [job for job in jobs if job["conclusion"] != "skipped"]
    finished = [job["completed_at"] for job in executed if job["completed_at"]]
    wall = elapsed(run["run_started_at"], max(finished, default=None))
    if wall is not None:
        metrics["Full workflow wall time"].append(Timings(wall, WORKFLOW_BUDGET))
    queue = [elapsed(job["created_at"], job["started_at"]) for job in executed]
    known = [seconds for seconds in queue if seconds is not None]
    execution = [elapsed(job["started_at"], job["completed_at"]) for job in executed]
    metrics["Total job execution (runner-seconds)"].append(
        Timings(sum(seconds for seconds in execution if seconds is not None))
    )
    if known:
        metrics["Longest job queue in run"].append(Timings(max(known), (10, 60)))


def report_metrics(metrics: dict[str, list[Timings]]) -> None:
    print("\n| Metric | Samples | Median (s) | p95 (s) | Budget median / p95 (s) |")
    print("| --- | ---: | ---: | ---: | ---: |")
    warnings = []
    for name, samples in sorted(metrics.items()):
        values = sorted(value.seconds for value in samples)
        count = len(values)
        median = statistics.median(values)
        p95 = values[math.ceil(0.95 * count) - 1] if count >= 10 else None
        p95_text = f"{p95:g}" if p95 is not None else "—"
        budget = samples[0].budget
        budget_text = f"{budget[0]} / {budget[1]}" if budget else "—"
        print(f"| {name} | {count} | {median:g} | {p95_text} | {budget_text} |")
        if budget and count >= 5 and (median > budget[0] or (p95 is not None and p95 > budget[1])):
            warnings.append(name)
    for name in warnings:
        print(f"\n- **Over budget:** {name}")


def report(repository: str, event: str, limit: int) -> None:
    branch = "&branch=main" if event == "push" else ""
    base = f"repos/{repository}/actions"
    response = github(
        f"{base}/workflows/ci.yml/runs?event={event}{branch}&status=completed&per_page={limit}"
    )
    runs = cast(list[Run], response["workflow_runs"])
    metrics: dict[str, list[Timings]] = defaultdict(list)
    outcomes = Counter(run["conclusion"] for run in runs)
    job_outcomes: Counter[str] = Counter()
    go_tool_cache: Counter[str] = Counter()
    previous_attempt_seconds = 0.0
    for run in runs:
        response = github(f"{base}/runs/{run['id']}/jobs?filter=all&per_page=100")
        jobs = cast(list[Job], response["jobs"])
        if len(jobs) != response["total_count"]:
            raise ValueError(f"Run {run['id']} has more than 100 job attempts")
        job_outcomes.update(job["conclusion"] for job in jobs)
        previous_attempt_seconds += sum(
            elapsed(job["started_at"], job["completed_at"]) or 0
            for job in jobs
            if job["run_attempt"] < run["run_attempt"] and job["conclusion"] != "skipped"
        )
        go_tool_cache.update(
            "hit" if step["conclusion"] == "skipped" else "miss"
            for job in jobs
            for step in job["steps"]
            if step["name"] == "Install pinned Go tools" and job["conclusion"] == "success"
        )
        record_run(run, jobs, metrics)

    print(f"\n### {event}: latest {len(runs)} completed runs")
    print(f"\n- Latest workflow outcomes: {dict(outcomes)}")
    print(f"- Job outcomes across all attempts: {dict(job_outcomes)}")
    print(f"- Runs with reruns: {sum(run['run_attempt'] > 1 for run in runs)}")
    print(f"- Runner-seconds spent on prior attempts: {previous_attempt_seconds:g}")
    print(f"- Go tool cache on successful jobs: {dict(go_tool_cache)}")
    report_metrics(metrics)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--limit", default=20, type=int, choices=range(1, 51), metavar="1-50")
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")
    print("## MatchForge CI performance")
    for event in ("pull_request", "push"):
        report(args.repo, event, args.limit)


if __name__ == "__main__":
    main()
