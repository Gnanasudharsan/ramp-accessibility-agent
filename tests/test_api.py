import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

from ramp.api.app import create_app
from ramp.api.store import AuditStore
from ramp.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"


async def _public(url: str) -> bool:
    return "internal" in url  # stand-in for DNS: "internal" hosts are private


@pytest.fixture
def api() -> Iterator[tuple[TestClient, list[tuple[str, str, int]]]]:
    get_settings.cache_clear()
    queued: list[tuple[str, str, int]] = []

    async def enqueue(audit_id: str, url: str, max_pages: int) -> None:
        queued.append((audit_id, url, max_pages))

    app = create_app(redis=FakeAsyncRedis(), enqueue=enqueue, is_private=_public)
    with TestClient(app) as client:
        yield client, queued


def test_submit_and_poll(api: tuple[TestClient, list[tuple[str, str, int]]]) -> None:
    client, queued = api
    created = client.post("/api/audits", json={"url": "https://example.org/", "max_pages": 2})
    assert created.status_code == 202
    body = created.json()
    assert queued == [(body["id"], "https://example.org/", 2)]
    status = client.get(body["status_url"]).json()
    assert status["status"] == "queued"
    assert client.get(f"/api/audits/{body['id']}/report").status_code == 404


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"url": "http://internal.example/"}, 422),  # private target refused (SSRF)
        ({"url": "ftp://example.org/"}, 422),  # only http(s)
        ({"url": "https://example.org/", "max_pages": 500}, 422),  # page cap
    ],
)
def test_rejects_unsafe_requests(
    api: tuple[TestClient, list[tuple[str, str, int]]], payload: dict[str, object], code: int
) -> None:
    client, queued = api
    assert client.post("/api/audits", json=payload).status_code == code
    assert queued == []


def test_rate_limit(api: tuple[TestClient, list[tuple[str, str, int]]]) -> None:
    client, _ = api
    limit = get_settings().api_audits_per_hour
    codes = [
        client.post("/api/audits", json={"url": "https://example.org/"}).status_code
        for _ in range(limit + 1)
    ]
    assert codes[:limit] == [202] * limit
    assert codes[-1] == 429


def test_unknown_audit(api: tuple[TestClient, list[tuple[str, str, int]]]) -> None:
    client, _ = api
    assert client.get("/api/audits/nope").status_code == 404
    assert client.get("/api/audits/nope/events").status_code == 404


async def test_events_replay_and_stop_at_terminal() -> None:
    store = AuditStore(FakeAsyncRedis())
    job = await store.create("https://example.org/", 1)
    await store.emit(job.id, "page", {"issues": 3})
    await store.emit(job.id, "done", {"issues": 3})
    await store.emit(job.id, "page", {"issues": 9})  # after terminal: never delivered
    kinds = [kind async for _, kind, _ in store.events(job.id)]
    assert kinds == ["queued", "page", "done"]
    # Reconnect after the first event: only what followed is replayed.
    ids = [eid async for eid, _, _ in store.events(job.id)]
    assert [k async for _, k, _ in store.events(job.id, after=ids[0])] == ["page", "done"]


@pytest.mark.integration
async def test_worker_runs_a_real_audit() -> None:
    from ramp.api.worker import run_audit
    from ramp.audit import launch_browser
    from ramp.evals.static_server import StaticServer

    redis = FakeAsyncRedis()
    store = AuditStore(redis)
    with StaticServer(FIXTURES / "site") as server:
        url = f"{server.url}/index.html"
        job = await store.create(url, 1)
        async with launch_browser() as browser:
            ctx = {"store": store, "browser": browser, "redis": redis}
            assert await run_audit(ctx, job.id, url, 1) == "done"
    final = await store.get(job.id)
    assert final is not None
    assert final.status == "done"
    assert final.summary is not None
    assert final.summary["issues"] > 0
    report = json.loads(await store.report(job.id) or "{}")
    assert report["pages"][0]["issues"]
    kinds = [k async for _, k, _ in store.events(job.id)]
    assert kinds == ["queued", "running", "page", "done"]


async def test_shared_limiter_spaces_requests_across_independent_crawls() -> None:
    """Two crawls of one host (separate jobs or workers) share one slot per interval."""
    import time

    from ramp.crawler.politeness import SharedRateLimiter

    redis = FakeAsyncRedis()
    a, b = SharedRateLimiter(redis, 0.3), SharedRateLimiter(redis, 0.3)
    started = time.monotonic()
    await a.wait("https://example.org/one")
    await b.wait("https://example.org/two")  # same host: must wait for the slot
    await b.wait("https://other.example/")  # different host: no wait
    elapsed = time.monotonic() - started
    assert 0.28 <= elapsed < 0.6
