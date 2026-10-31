"""Navigation de l'application : une seule définition pour la barre du bas et le menu latéral."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    label: str
    icon: str
    url_name: str
    prefixes: tuple[str, ...]  # noms de routes (ou préfixes) pour lesquels l'entrée est active
    excluded: tuple[str, ...] = ()
    mobile: bool = (
        True  # présent dans la barre du bas (sinon : menu latéral et page « Plus » seulement)
    )


PRIMARY = (
    NavItem("Accueil", "home", "core:home", ("core:home",)),
    NavItem("Menus", "calendar", "planner:", ("planner:",)),
    NavItem("Courses", "cart", "shopping:index", ("shopping:",), ("shopping:pantry",)),
    NavItem("Recettes", "book", "catalog:", ("catalog:",)),
)
MORE = NavItem(
    "Plus",
    "dots",
    "core:more",
    ("core:more", "households:", "shopping:pantry", "mfa_", "account_"),
)
HOUSEHOLD = (
    NavItem(
        "Foyer",
        "home",
        "households:home",
        ("households:home", "households:invitation", "households:member"),
        mobile=False,
    ),
    NavItem(
        "Convives",
        "users",
        "households:diners",
        ("households:diner", "households:restriction"),
        mobile=False,
    ),
    NavItem("Équipements", "pot", "households:equipment", ("households:equipment",), mobile=False),
    NavItem(
        "Préférences",
        "sliders",
        "households:preferences",
        ("households:preferences",),
        mobile=False,
    ),
    NavItem("Placard", "box", "shopping:pantry", ("shopping:pantry",), mobile=False),
)
ACCOUNT = (NavItem("Sécurité", "shield", "mfa_index", ("mfa_", "account_"), mobile=False),)

# Un `url_name` terminé par « : » désigne l'espace de noms : on pointe alors vers sa liste.
LIST_ROUTES = {"planner:": "planner:list", "catalog:": "catalog:list"}


def url_for(item: NavItem) -> str:
    return LIST_ROUTES.get(item.url_name, item.url_name)


def is_active(item: NavItem, view_name: str) -> bool:
    if any(view_name.startswith(excluded) for excluded in item.excluded):
        return False
    return any(view_name.startswith(prefix) for prefix in item.prefixes)
