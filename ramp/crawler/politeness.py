"""Crawl etiquette: robots.txt (RFC 9309, via protego) and a per-host rate limiter."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from protego import Protego


@dataclass
class RobotsPolicy:
    """robots.txt rules for one origin.

    RFC 9309: a 4xx response means no restrictions; a 5xx or network failure means
    "assume complete disallow". protego supports ``*`` and ``$`` wildcards, which the standard
    library parser does not.
    """

    user_agent: str
    rules: Protego | None
    disallow_all: bool = False

    def allowed(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.rules is None:
            return True
        return bool(self.rules.can_fetch(url, self.user_agent))

    @property
    def crawl_delay(self) -> float | None:
        if self.rules is None:
            return None
        delay = self.rules.crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None

    @classmethod
    def from_text(cls, text: str, user_agent: str) -> RobotsPolicy:
        return cls(user_agent=user_agent, rules=Protego.parse(text))

    @classmethod
    async def fetch(cls, origin: str, user_agent: str, client: httpx.AsyncClient) -> RobotsPolicy:
        try:
            response = await client.get(
                f"{origin}/robots.txt", headers={"User-Agent": user_agent}, follow_redirects=True
            )
        except httpx.HTTPError:
            return cls(user_agent=user_agent, rules=None, disallow_all=True)
        if response.status_code >= 500:
            return cls(user_agent=user_agent, rules=None, disallow_all=True)
        if response.status_code >= 400:
            return cls(user_agent=user_agent, rules=None)
        return cls.from_text(response.text, user_agent)


@dataclass
class RateLimiter:
    """At most one request per ``min_interval`` seconds per host.

    The clock and sleep are injectable so tests run instantly and deterministically (a fake
    sleep should advance the fake clock).
    """

    min_interval: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], object] = asyncio.sleep
    _last: dict[str, float] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    async def wait(self, url: str) -> float:
        """Block until a request to ``url``'s host is allowed; return seconds waited."""
        host = urlsplit(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = self.clock()
            last = self._last.get(host)
            waited = 0.0
            if last is not None and now - last < self.min_interval:
                waited = self.min_interval - (now - last)
                result = self.sleep(waited)
                if asyncio.iscoroutine(result):
                    await result
            self._last[host] = self.clock()
            return waited
