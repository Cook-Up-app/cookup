"""robots.txt : analyse avec jokers (Protego) et règle de repli de la RFC 9309."""

import time
from collections.abc import Callable
from dataclasses import dataclass

from protego import Protego

from .exceptions import FetchRefused

ROBOTS_TTL_SECONDS = 24 * 60 * 60
NOT_FOUND_STATUSES = frozenset({404, 410})


@dataclass(frozen=True)
class RobotsRules:
    parser: Protego | None  # None : tout est autorisé (fichier absent)
    allow_all: bool

    def can_fetch(self, url: str, user_agent: str) -> bool:
        return self.allow_all or (
            self.parser is not None and self.parser.can_fetch(url, user_agent)
        )

    def crawl_delay(self, user_agent: str) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(user_agent)
        return float(delay) if delay else None


class RobotsPolicy:
    """Charge robots.txt une fois par hôte (cache en mémoire de l'instance, 24 h).

    Fichier absent (404/410) : tout est permis. Fichier injoignable ou en erreur serveur :
    tout est interdit, comme l'exige la RFC 9309.
    """

    def __init__(
        self,
        load: Callable[[str], tuple[int, str]],
        user_agent: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._user_agent = user_agent
        self._clock = clock
        self._cache: dict[str, tuple[float, RobotsRules]] = {}

    def rules_for(self, origin: str) -> RobotsRules:
        cached = self._cache.get(origin)
        if cached and self._clock() - cached[0] < ROBOTS_TTL_SECONDS:
            return cached[1]
        rules = self._fetch(origin)
        self._cache[origin] = (self._clock(), rules)
        return rules

    def _fetch(self, origin: str) -> RobotsRules:
        status, body = self._load(f"{origin}/robots.txt")
        if status in NOT_FOUND_STATUSES:
            return RobotsRules(parser=None, allow_all=True)
        if status != 200:
            return RobotsRules(parser=None, allow_all=False)
        return RobotsRules(parser=Protego.parse(body), allow_all=False)

    def ensure_allowed(self, origin: str, url: str) -> RobotsRules:
        rules = self.rules_for(origin)
        if not rules.can_fetch(url, self._user_agent):
            raise FetchRefused("Interdit par robots.txt.")
        return rules
