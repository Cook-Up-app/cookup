"""Phrases d'explication de l'échec de génération (texte d'interface, en français)."""

from .engine import FailureReport, Violation

LABELS = {
    Violation.ALLERGEN: "les allergies et restrictions déclarées",
    Violation.UNCERTAIN_ALLERGENS: "les ingrédients non reconnus (par prudence avec une allergie)",
    Violation.DIET: "les régimes",
    Violation.UNCERTAIN_DIET: "les ingrédients non reconnus (par prudence avec un régime)",
    Violation.EQUIPMENT: "les équipements manquants ou exclus",
    Violation.SOURCE: "le mode de source choisi",
    Violation.TIME: "le temps maximal",
    Violation.MEAL_TYPE: "le type de repas",
    Violation.PORTIONS: "le nombre de portions",
    Violation.EXCLUDED: "les recettes exclues",
    Violation.RECENT: "les recettes servies récemment",
}


def describe_failure(report: FailureReport) -> str:
    """« 71 % des recettes sont écartées par … » puis une piste pour s'en sortir."""
    reasons = " et ".join(LABELS[v] for v in report.top_reasons(2))
    if report.total and report.remaining:
        return (
            f"Pas assez de recettes différentes : {report.remaining} seulement conviennent "
            f"à ce créneau ({report.eliminated_percent} % sont écartées par {reasons}). "
            "Importez davantage de recettes ou relâchez une contrainte."
        )
    return (
        f"{report.eliminated_percent} % des recettes sont écartées par {reasons}. "
        "Importez davantage de recettes ou relâchez une contrainte."
    )
