"""Vocabulaire partagé : ce qu'un mot désigne (synonymes d'allergènes, membres des familles).

Données seules : la reconnaissance d'un texte saisi est dans `households.restrictions`.
Les formes sont écrites au singulier ; la comparaison ignore accents, casse et pluriel.
"""

from dataclasses import dataclass

from .reference import Allergen, FoodGroup

# Autres façons de nommer chacun des 14 allergènes (le libellé officiel est toujours reconnu).
ALLERGEN_SYNONYMS: dict[Allergen, tuple[str, ...]] = {
    Allergen.GLUTEN: ("gluten", "blé", "seigle", "orge", "avoine", "épeautre"),
    Allergen.CRUSTACEANS: ("crustacé", "crevette", "homard", "crabe", "langoustine"),
    Allergen.EGGS: ("oeuf", "œuf"),
    Allergen.FISH: ("poisson",),
    Allergen.PEANUTS: ("arachide", "cacahuète", "cacahuete"),
    Allergen.SOY: ("soja",),
    Allergen.MILK: ("lait", "lactose", "produit laitier", "laitage"),
    Allergen.TREE_NUTS: ("fruit à coque", "noix", "noisette", "amande", "pistache"),
    Allergen.CELERY: ("céleri",),
    Allergen.MUSTARD: ("moutarde",),
    Allergen.SESAME: ("sésame",),
    Allergen.SULPHITES: ("sulfite", "sulfites"),
    Allergen.LUPIN: ("lupin",),
    Allergen.MOLLUSCS: ("mollusque", "moule", "huître", "calamar", "poulpe"),
}


@dataclass(frozen=True)
class GroupDefinition:
    synonyms: tuple[str, ...]  # autres noms de la famille
    members: tuple[str, ...]  # aliments qu'elle exclut (un mot ou plusieurs, au singulier)
    allergens: tuple[Allergen, ...] = ()  # allergènes déclarés qu'elle recouvre


FOOD_GROUPS: dict[FoodGroup, GroupDefinition] = {
    FoodGroup.LEGUMES_PULSES: GroupDefinition(
        synonyms=("légumineuse", "légume sec", "légumes secs"),
        members=(
            "lentille",
            "pois chiche",
            "pois cassé",
            "petit pois",
            "pois",
            "haricot",
            "flageolet",
            "fève",
            "soja",
            "lupin",
            "cacahuète",
            "arachide",
            "edamame",
            "tofu",
            "houmous",
        ),
        allergens=(Allergen.PEANUTS, Allergen.SOY, Allergen.LUPIN),
    ),
    FoodGroup.CITRUS: GroupDefinition(
        synonyms=("agrume",),
        members=(
            "citron",
            "orange",
            "pamplemousse",
            "mandarine",
            "clémentine",
            "lime",
            "pomelo",
            "bergamote",
            "yuzu",
            "kumquat",
        ),
    ),
    FoodGroup.NIGHTSHADES: GroupDefinition(
        synonyms=("solanacée", "solanacees"),
        members=(
            "tomate",
            "pomme de terre",
            "aubergine",
            "poivron",
            "piment",
            "paprika",
            "cayenne",
            "harissa",
            "goji",
        ),
    ),
    FoodGroup.CRUCIFEROUS: GroupDefinition(
        synonyms=("crucifère", "crucifere", "chou"),
        members=(
            "chou",
            "brocoli",
            "chou-fleur",
            "radis",
            "navet",
            "roquette",
            "cresson",
            "colza",
            "choucroute",
            "rutabaga",
            "wasabi",
        ),
    ),
    FoodGroup.ALLIUMS: GroupDefinition(
        synonyms=("alliacée", "alliacees", "ail et oignon"),
        members=("ail", "oignon", "échalote", "poireau", "ciboulette", "cive", "ciboule"),
    ),
    FoodGroup.MUSHROOMS: GroupDefinition(
        synonyms=("champignon", "champignons"),
        members=(
            "champignon",
            "cèpe",
            "girolle",
            "morille",
            "shiitake",
            "pleurote",
            "truffe",
            "chanterelle",
            "trompette de la mort",
        ),
    ),
    FoodGroup.RED_FRUITS: GroupDefinition(
        synonyms=("fruit rouge", "baie", "petits fruits"),
        members=(
            "fraise",
            "framboise",
            "myrtille",
            "cerise",
            "mûre",
            "groseille",
            "cassis",
            "airelle",
        ),
    ),
    FoodGroup.STONE_FRUITS: GroupDefinition(
        synonyms=("fruit à noyau",),
        members=("pêche", "abricot", "prune", "pruneau", "cerise", "nectarine", "brugnon"),
    ),
    FoodGroup.SEAFOOD: GroupDefinition(
        synonyms=("fruit de mer", "crustacés et mollusques"),
        members=(
            "crevette",
            "moule",
            "huître",
            "crabe",
            "homard",
            "langoustine",
            "calamar",
            "poulpe",
            "coquille saint-jacques",
            "saint-jacques",
            "palourde",
            "bulot",
            "seiche",
            "surimi",
        ),
        allergens=(Allergen.CRUSTACEANS, Allergen.MOLLUSCS),
    ),
}
