import socket
from datetime import UTC, datetime, timedelta

import pytest

from apps.sources.http import FetchResult, PoliteFetcher, RawResponse
from apps.sources.ratelimit import DatabaseRateLimiter

USER_AGENT = "CookupBot/0.1 (+https://example.test; contact: test@example.test)"
PUBLIC_IP = "93.184.216.34"
ROBOTS = """User-agent: *
Disallow: /mon-espace/*
Disallow: /recettes/recette-impression_*
Disallow: /recettes/recherche.aspx?type=*
Disallow: /recettes/recherche.aspx?aqt=*page*
Disallow: /recettes/recherche.aspx?aqt=*start*
"""


class FakeTransport:
    """Réponses préparées par URL ; robots.txt absent (404) par défaut."""

    def __init__(self, pages: dict[str, RawResponse] | None = None) -> None:
        self.pages = pages or {}
        self.requested: list[str] = []

    def get(self, url: str, headers: dict[str, str], *args, **kwargs) -> RawResponse:
        self.requested.append(url)
        if url in self.pages:
            return self.pages[url]
        return RawResponse(404, {}, b"")


def html(body: str = "<html></html>", status: int = 200, **headers: str) -> RawResponse:
    return RawResponse(
        status, {"content-type": "text/html; charset=utf-8", **headers}, body.encode()
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Tout nom se résout en adresse publique, sauf si le test en décide autrement."""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", (PUBLIC_IP, port))]
    )


@pytest.fixture
def make_fetcher(clock, db):
    def build(pages=None, domains=frozenset({"marmiton.org"}), robots: str | None = ROBOTS):
        transport = FakeTransport(pages)
        if robots is not None:
            transport.pages["https://www.marmiton.org/robots.txt"] = RawResponse(
                200, {"content-type": "text/plain"}, robots.encode()
            )
        limiter = DatabaseRateLimiter("marmiton", sleep=clock.sleep, now=clock)
        fetcher = PoliteFetcher(
            user_agent=USER_AGENT, allowed_domains=domains, limiter=limiter, transport=transport
        )
        return fetcher, transport

    return build


__all__ = ["FetchResult", "html"]
