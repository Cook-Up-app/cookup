"""Saisonnalité simplifiée des fruits et légumes (mois de 1 à 12, plages circulaires)."""

SEASONS: dict[str, tuple[int, int]] = {
    "courgette": (6, 9), "tomate": (6, 9), "tomate cerise": (6, 9), "aubergine": (7, 9),
    "poivron": (7, 9), "concombre": (6, 8), "fraise": (5, 7), "framboise": (6, 8),
    "myrtille": (6, 8), "pêche": (6, 9), "abricot": (6, 8), "melon": (6, 9),
    "raisin": (8, 10), "pomme": (9, 3), "poire": (9, 2), "courge": (9, 12),
    "poireau": (10, 4), "chou-fleur": (10, 3), "chou": (10, 3), "navet": (10, 3),
    "betterave": (10, 3), "épinards": (3, 6), "asperge": (4, 6), "radis": (4, 6),
    "haricots verts": (6, 9), "petits pois": (5, 7), "champignon": (9, 11),
    "orange": (12, 3), "citron": (11, 4), "patate douce": (9, 12), "brocoli": (10, 3),
    "mangue": (5, 8), "ananas": (11, 3), "céleri-rave": (10, 3), "fenouil": (10, 3),
}  # fmt: skip


def in_season(name: str, month: int) -> bool:
    window = SEASONS.get(name)
    if window is None:
        return False
    start, end = window
    return start <= month <= end if start <= end else month >= start or month <= end


def seasonal_names(month: int) -> set[str]:
    return {name for name in SEASONS if in_season(name, month)}
