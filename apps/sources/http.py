"""Récupération HTTP polie : SSRF, robots.txt, débit, taille et durée plafonnées."""

import http.client
import zlib
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from .exceptions import FetchFailed, FetchRefused, SourceUnavailable
from .ratelimit import DatabaseRateLimiter
from .robots import RobotsPolicy
from .security import ensure_public_address, validate_url

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 3
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
PAUSE_STATUSES = frozenset({429, 503})
DEFAULT_PAUSE_SECONDS = 6 * 60 * 60
ACCEPTED_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    text: str


class Transport(Protocol):
    def get(self, url: str, headers: dict[str, str]) -> RawResponse: ...


class HttpTransport:
    """Transport réel : vérifie l'adresse réellement jointe avant d'envoyer quoi que ce soit."""

    def get(self, url: str, headers: dict[str, str]) -> RawResponse:
        parts = urlsplit(url)
        connection_class = (
            http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_class(parts.hostname, parts.port, timeout=TIMEOUT_SECONDS)
        try:
            connection.connect()
            ensure_public_address(connection.sock.getpeername()[0])
            target = parts.path or "/"
            connection.request(
                "GET", f"{target}?{parts.query}" if parts.query else target, headers=headers
            )
            response = connection.getresponse()
            body = _read_capped(response)
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return RawResponse(response.status, response_headers, body)
        except OSError as error:
            raise FetchFailed("Connexion impossible ou interrompue.") from error
        finally:
            connection.close()


def _read_capped(response: http.client.HTTPResponse) -> bytes:
    body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise FetchFailed("Réponse trop volumineuse.")
    if (response.getheader("Content-Encoding") or "").lower() in {"gzip", "x-gzip"}:
        decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
        body = decompressor.decompress(body, MAX_BYTES + 1)
        if len(body) > MAX_BYTES or decompressor.unconsumed_tail:
            raise FetchFailed("Réponse décompressée trop volumineuse.")
    return body


class PoliteFetcher:
    """Chaque requête (robots.txt compris) passe par la liste blanche, le débit et SSRF."""

    def __init__(
        self,
        *,
        user_agent: str,
        allowed_domains: frozenset[str],
        limiter: DatabaseRateLimiter,
        transport: Transport | None = None,
    ) -> None:
        if "contact" not in user_agent.lower():
            raise SourceUnavailable("User-Agent sans contact : configurez SOURCES_CONTACT.")
        self._user_agent = user_agent
        self._allowed = allowed_domains
        self._limiter = limiter
        self._transport = transport or HttpTransport()
        self._robots = RobotsPolicy(self._load_robots, user_agent)

    def get(self, url: str) -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response = self._checked_request(current)
            if response.status in REDIRECT_STATUSES and "location" in response.headers:
                current = urljoin(current, response.headers["location"])
                continue
            return self._finish(current, response)
        raise FetchFailed("Trop de redirections.")

    def _checked_request(self, url: str) -> RawResponse:
        validate_url(url, self._allowed)
        parts = urlsplit(url)
        rules = self._robots.ensure_allowed(f"{parts.scheme}://{parts.netloc}", url)
        return self._request(url, rules.crawl_delay(self._user_agent))

    def _request(self, url: str, crawl_delay: float | None = None) -> RawResponse:
        self._limiter.wait(crawl_delay)
        response = self._transport.get(url, self._headers())
        if response.status in PAUSE_STATUSES:
            self._limiter.pause(_retry_after(response))
            raise SourceUnavailable(f"La source a répondu {response.status} : pause.")
        return response

    def _load_robots(self, robots_url: str) -> tuple[int, str]:
        validate_url(robots_url, self._allowed)
        try:
            response = self._request(robots_url)
        except FetchFailed:
            return 599, ""  # injoignable : tout interdire (RFC 9309)
        return response.status, response.body.decode("utf-8", errors="replace")

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Accept-Encoding": "gzip",
        }

    @staticmethod
    def _finish(url: str, response: RawResponse) -> FetchResult:
        if response.status != 200:
            raise FetchFailed(f"Statut HTTP {response.status}.")
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type and content_type not in ACCEPTED_TYPES:
            raise FetchRefused("Type de contenu inattendu.")
        return FetchResult(url, response.status, response.body.decode("utf-8", errors="replace"))


def _retry_after(response: RawResponse) -> float:
    value = response.headers.get("retry-after", "")
    return float(value) if value.isdigit() else DEFAULT_PAUSE_SECONDS
