import uuid

from django.conf import settings
from django.db import models

from apps.core.reference import RecipeSource


class ImportJob(models.Model):
    """Trace d'un import : une recette (ou une recherche) = une requête."""

    class Kind(models.TextChoices):
        RECIPE = "recipe", "Recette"
        SEARCH = "search", "Recherche"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        DONE = "done", "Terminé"
        FAILED = "failed", "Échec"
        SKIPPED = "skipped", "Ignoré"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=20, choices=RecipeSource.choices)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.RECIPE)
    target = models.CharField("URL ou requête", max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    recipe = models.ForeignKey(
        "catalog.Recipe", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "kind", "target"], name="import_job_target_unique"
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="import_job_queue_idx")]

    def __str__(self) -> str:
        return f"{self.source}:{self.target}"


class SourceState(models.Model):
    """État partagé entre invocations serverless : débit, découverte, pause après blocage."""

    source = models.CharField(max_length=20, primary_key=True)
    last_request_at = models.DateTimeField(null=True, blank=True)
    last_discovery_at = models.DateTimeField(null=True, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.source
