"""Débit poli partagé entre invocations serverless : l'état vit en base, pas en mémoire."""

import time
from collections.abc import Callable
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .exceptions import SourceUnavailable
from .models import SourceState

DEFAULT_MIN_INTERVAL = 1.0  # 1 requête par seconde au maximum (SPEC section 14)


class DatabaseRateLimiter:
    def __init__(
        self,
        source: str,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable = timezone.now,
    ) -> None:
        self.source = source
        self.min_interval = min_interval
        self._sleep = sleep
        self._now = now

    def wait(self, min_interval: float | None = None) -> None:
        """Bloque jusqu'à ce qu'une requête soit permise, puis la comptabilise."""
        interval = max(self.min_interval, min_interval or 0)
        with transaction.atomic():
            state, _ = SourceState.objects.select_for_update().get_or_create(source=self.source)
            now = self._now()
            if state.cooldown_until and state.cooldown_until > now:
                raise SourceUnavailable("Source en pause après un refus ou une erreur.")
            if state.last_request_at:
                remaining = (
                    state.last_request_at + timedelta(seconds=interval) - now
                ).total_seconds()
                if remaining > 0:
                    self._sleep(remaining)
            state.last_request_at = self._now()
            state.save(update_fields=["last_request_at"])

    def pause(self, seconds: float) -> None:
        """Met la source en pause (Retry-After, blocage) : aucune requête avant l'échéance."""
        until = self._now() + timedelta(seconds=seconds)
        SourceState.objects.update_or_create(source=self.source, defaults={"cooldown_until": until})
