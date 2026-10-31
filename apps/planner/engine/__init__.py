"""Moteur de menus : Python pur, sans Django, donc testable sans base de données."""

from .failure import FailureReport, NotEnoughCandidates
from .planning import apply_leftovers, assign_modes
from .rules import Violation, is_allowed, violations
from .selection import candidates_for, generate, suggest_alternatives
from .types import (
    Assignment,
    Context,
    DinerView,
    EngineSettings,
    GeneratedPlan,
    History,
    RecipeView,
    SlotSpec,
)

__all__ = [
    "Assignment",
    "Context",
    "DinerView",
    "EngineSettings",
    "FailureReport",
    "GeneratedPlan",
    "History",
    "NotEnoughCandidates",
    "RecipeView",
    "SlotSpec",
    "Violation",
    "apply_leftovers",
    "assign_modes",
    "candidates_for",
    "generate",
    "is_allowed",
    "suggest_alternatives",
    "violations",
]
