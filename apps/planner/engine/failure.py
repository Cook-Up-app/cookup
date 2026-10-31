"""Cas d'échec : le moteur n'invente pas un menu incomplet, il explique ce qui bloque."""

from collections import Counter
from dataclasses import dataclass

from .rules import Violation, violations
from .types import Context, RecipeView, SlotSpec


@dataclass(frozen=True)
class FailureReport:
    slot_key: str
    total: int  # recettes du catalogue
    remaining: int  # recettes encore permises pour ce créneau
    eliminated_by: tuple[tuple[Violation, int], ...]  # contrainte -> nombre de recettes écartées

    @property
    def eliminated_percent(self) -> int:
        return round(100 * (self.total - self.remaining) / self.total) if self.total else 0

    def top_reasons(self, count: int = 2) -> list[Violation]:
        return [violation for violation, _ in self.eliminated_by[:count]]


class NotEnoughCandidates(Exception):  # noqa: N818 - nom métier fixé par la spec
    def __init__(self, report: FailureReport) -> None:
        super().__init__(f"Pas assez de recettes pour {report.slot_key}")
        self.report = report


def analyse(
    slot: SlotSpec, recipes: list[RecipeView], ctx: Context, remaining: int
) -> FailureReport:
    """Compte, contrainte par contrainte, combien de recettes elle écarte à elle seule."""
    counts: Counter[Violation] = Counter()
    for recipe in recipes:
        counts.update(set(violations(recipe, slot, ctx)))
    ordered = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0].value)))
    return FailureReport(slot.key, len(recipes), remaining, ordered)
