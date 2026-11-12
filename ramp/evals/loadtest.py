"""Load test for the audit API: ``make loadtest`` (see ``infra/loadtest/compose.loadtest.yml``).

For each concurrency level, ``concurrency`` simulated clients each submit audits back to back
(one page from the local benchmark copy) and poll until done. Measured per level:

- submit latency (``POST /api/audits``: validation, rate limit, enqueue) p50/p95,
- status-read latency (``GET /api/audits/{id}``) p50/p95 while the queue is busy,
- end-to-end audit time p50/p95 and how much of it was queue wait,
- throughput (audits completed per minute) and error rate.

The target is a static site in its own container, so no load ever reaches a real website.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from ramp.evals.metrics import percentile

RESULTS = Path(__file__).resolve().parents[2] / "evals" / "results" / "loadtest"
PAGES = [
    "synthetic/s01-img-no-alt.html",
    "synthetic/s03-low-contrast.html",
    "synthetic/v04-click-here.html",
    "synthetic/n05-clean-article.html",
]


@dataclass
class LevelStats:
    concurrency: int
    submit_s: list[float] = field(default_factory=list)
    status_s: list[float] = field(default_factory=list)
    end_to_end_s: list[float] = field(default_factory=list)
    queue_wait_s: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    wall_s: float = 0.0

    def summary(self) -> dict[str, Any]:
        def p(values: list[float], q: int) -> float | None:
            value = percentile(values, q) if values else None
            return round(value, 3) if value is not None else None

        done = len(self.end_to_end_s)
        return {
            "concurrency": self.concurrency,
            "audits_completed": done,
            "errors": len(self.errors),
            "error_rate": len(self.errors) / (done + len(self.errors))
            if done + len(self.errors)
            else 0.0,
            "throughput_per_min": round(60 * done / self.wall_s, 2) if self.wall_s else 0.0,
            "submit_p50_s": p(self.submit_s, 50),
            "submit_p95_s": p(self.submit_s, 95),
            "status_p50_s": p(self.status_s, 50),
            "status_p95_s": p(self.status_s, 95),
            "end_to_end_p50_s": p(self.end_to_end_s, 50),
            "end_to_end_p95_s": p(self.end_to_end_s, 95),
            "queue_wait_p50_s": p(self.queue_wait_s, 50),
            "queue_wait_p95_s": p(self.queue_wait_s, 95),
            "error_examples": self.errors[:3],
        }


async def one_audit(
    client: httpx.AsyncClient, api: str, target: str, stats: LevelStats, timeout_s: float
) -> None:
    started = time.perf_counter()
    response = await client.post(f"{api}/api/audits", json={"url": target, "max_pages": 1})
    stats.submit_s.append(time.perf_counter() - started)
    if response.status_code != 202:
        stats.errors.append(f"submit {response.status_code}: {response.text[:120]}")
        return
    status_url = f"{api}{response.json()['status_url']}"
    running_at: float | None = None
    while time.perf_counter() - started < timeout_s:
        t0 = time.perf_counter()
        status = await client.get(status_url)
        stats.status_s.append(time.perf_counter() - t0)
        state = status.json().get("status")
        if state == "running" and running_at is None:
            running_at = time.perf_counter()
        if state == "done":
            stats.end_to_end_s.append(time.perf_counter() - started)
            stats.queue_wait_s.append((running_at or time.perf_counter()) - started)
            return
        if state == "failed":
            stats.errors.append(f"audit failed: {status.json().get('error', '')[:120]}")
            return
        await asyncio.sleep(0.25)
    stats.errors.append("timeout")


async def run_level(
    api: str, sites: list[str], concurrency: int, audits_per_client: int, timeout_s: float
) -> LevelStats:
    stats = LevelStats(concurrency)

    async def client_loop(n: int) -> None:
        # Each simulated client has its own connection pool, like separate browsers would.
        async with httpx.AsyncClient(timeout=30) as client:
            for k in range(audits_per_client):
                page = PAGES[(n + k) % len(PAGES)]
                site = sites[n % len(sites)]
                await one_audit(client, api, f"{site}/{page}", stats, timeout_s)

    started = time.perf_counter()
    await asyncio.gather(*(client_loop(n) for n in range(concurrency)))
    stats.wall_s = time.perf_counter() - started
    return stats


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Load test: audit API",
        "",
        f"Run {result['run_at']} · {result['workers']} worker(s), {result['jobs_per_worker']} "
        f"concurrent jobs each · {result['audits_per_client']} one-page audits per client · "
        f"{result['sites']} target host(s), all a local static copy of the benchmark pages.",
        "",
        "| Clients | Audits | Errors | Audits/min | Submit p50 / p95 (s) | Status read p50 / p95 "
        "(s) | End-to-end p50 / p95 (s) | Queue wait p50 / p95 (s) |",
        "|---:|---:|---:|---:|---|---|---|---|",
    ]
    for lvl in result["levels"]:
        lines.append(
            f"| {lvl['concurrency']} | {lvl['audits_completed']} | {lvl['errors']} | "
            f"{lvl['throughput_per_min']} | {lvl['submit_p50_s']} / {lvl['submit_p95_s']} | "
            f"{lvl['status_p50_s']} / {lvl['status_p95_s']} | "
            f"{lvl['end_to_end_p50_s']} / {lvl['end_to_end_p95_s']} | "
            f"{lvl['queue_wait_p50_s']} / {lvl['queue_wait_p95_s']} |"
        )
    lines += [
        "",
        "End-to-end time includes the crawler's politeness rules: a robots.txt fetch per audit "
        "and at most one page request per second per host, shared by every job and worker.",
    ]
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    levels = []
    for concurrency in args.levels:
        stats = await run_level(
            args.api, args.sites, concurrency, args.audits_per_client, args.timeout
        )
        levels.append(stats.summary())
        print(json.dumps(levels[-1]))
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "api": args.api,
        "workers": args.workers,
        "jobs_per_worker": args.jobs_per_worker,
        "audits_per_client": args.audits_per_client,
        "sites": len(args.sites),
        "levels": levels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8088")
    parser.add_argument(
        "--sites",
        nargs="+",
        default=[f"http://site-{n}" for n in range(1, 9)],
        help="Target hosts; client n uses sites[n %% len]. One host measures politeness.",
    )
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 4, 8, 16])
    parser.add_argument("--audits-per-client", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--workers", type=int, default=1, help="Recorded in the results.")
    parser.add_argument("--jobs-per-worker", type=int, default=2, help="Recorded in the results.")
    parser.add_argument("--name", default="latest")
    args = parser.parse_args()
    result = asyncio.run(main_async(args))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{args.name}.json").write_text(json.dumps(result, indent=2) + "\n")
    (RESULTS / f"{args.name}.md").write_text(render(result))
    print(render(result))


if __name__ == "__main__":
    main()
