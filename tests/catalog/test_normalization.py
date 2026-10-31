from decimal import Decimal

import pytest

from apps.catalog.matching import IngredientIndex
from apps.catalog.normalization import parse_line, split_compound, to_base
from apps.catalog.seeding import parse_catalog
from apps.catalog.text import fold, stem_key


@pytest.fixture(scope="module")
def index() -> IngredientIndex:
    entries = [(i, e["name"], e["aliases"]) for i, e in enumerate(parse_catalog())]
    return IngredientIndex(entries)


@pytest.mark.parametrize(
    ("line", "quantity", "unit", "name"),
    [
        ("2 c. à soupe d'huile d'olive", "2", "c. à soupe", "huile d olive"),
        ("200 g de farine", "200", "g", "farine"),
        ("1/2 oignon", "0.5", None, "oignon"),
        ("1 pincée de sel", "1", "pincée", "sel"),
        ("3 gousses d'ail", "3", "gousse", "ail"),
        ("500g de tomates", "500", "g", "tomates"),
        ("1,5 L de lait", "1.5", "l", "lait"),
        ("250ml de lait", "250", "ml", "lait"),
        ("2 à 3 pommes de terre", "3", None, "pommes de terre"),
        ("1 c.à.s. d'huile", "1", "c. à soupe", "huile"),
        ("1 càs de miel", "1", "c. à soupe", "miel"),
        ("½ botte de ciboulette", "0.5", "botte", "ciboulette"),
        ("1 1/2 verre de lait", "1.5", "verre", "lait"),
        ("une pincée de sel", "1", "pincée", "sel"),
        ("un peu de persil", None, None, "persil"),
        ("quelques feuilles de basilic", None, "feuille", "basilic"),
        ("2 cuillères à café de curry", "2", "c. à café", "curry"),
        ("100 g de gruyère râpé", "100", "g", "gruyère râpé"),
        ("1 boîte de tomates concassées (400 g)", "1", "boîte", "tomates concassées"),
        ("3 oeufs entiers", "3", None, "oeufs entiers"),
        ("farine, tamisée", None, None, "farine"),
    ],
)
def test_parse_french_lines(line, quantity, unit, name):
    parsed = parse_line(line)

    assert parsed.quantity == (Decimal(quantity) if quantity else None)
    assert (parsed.unit.code if parsed.unit else None) == unit
    assert parsed.name == name


def test_optional_marker_is_detected_and_removed():
    parsed = parse_line("1 c. à café de piment (facultatif)")

    assert parsed.is_optional
    assert parsed.name == "piment"


def test_compound_lines_without_quantity_are_split():
    assert split_compound("Sel, poivre") == ["Sel", "poivre"]
    assert split_compound("200 g de farine, tamisée") == ["200 g de farine, tamisée"]


@pytest.mark.parametrize(
    ("line", "base_quantity", "base_unit"),
    [
        ("2 c. à soupe d'huile", "30", "ml"),
        ("30 ml d'huile", "30", "ml"),
        ("2 kg de pommes de terre", "2000", "g"),
        ("10 cl de crème", "100", "ml"),
        ("3 gousses d'ail", "3", "pièce"),
        ("2 carottes", "2", "pièce"),
        ("1 pincée de sel", None, ""),
    ],
)
def test_conversion_to_base_units(line, base_quantity, base_unit):
    parsed = parse_line(line)

    quantity, unit = to_base(parsed.quantity, parsed.unit)

    assert quantity == (Decimal(base_quantity) if base_quantity else None)
    assert unit == base_unit


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("huile d'olive", "huile olive"),
        ("Œufs", "oeuf"),
        ("pommes de terre", "pomme terre"),
        ("riz", "riz"),
        ("pois chiches", "pois chiche"),
    ],
)
def test_stem_key(name, expected):
    assert stem_key(name) == expected
    assert fold("Crème fraîche") == "creme fraiche"


@pytest.mark.parametrize(
    ("name", "canonical", "exact"),
    [
        ("farine", "farine", True),
        ("oeufs entiers", "œuf", True),
        ("pommes de terre", "pomme de terre", True),
        ("gruyère râpé", "fromage râpé", True),  # alias exact « gruyère » + descripteur inoffensif
        ("filet de poulet", "poulet", True),
        ("tomates concassées", "tomates concassées", True),
        ("lait de coco", "lait de coco", True),
        ("beurre de cacahuète", "beurre de cacahuète", True),
    ],
)
def test_matching_prefers_the_most_specific_catalogue_entry(index, name, canonical, exact):
    names = {i: e["name"] for i, e in enumerate(parse_catalog())}

    match = index.find(name)

    assert match is not None
    assert names[match.ingredient_id] == canonical
    assert match.exact is exact


def test_partial_match_with_unknown_word_is_flagged_for_review(index):
    match = index.find("beurre de karité")  # « beurre » reconnu, mais pas « karité »

    assert match is not None
    assert match.exact is False


def test_unknown_ingredient_is_not_guessed(index):
    assert index.find("pierre de lune") is None


@pytest.mark.parametrize(
    ("line", "unit", "canonical"),
    [  # lignes observées sur de vraies pages de recettes
        ("1 rouleau de pâtes feuilletées", "rouleau", "pâte feuilletée"),
        ("0,5 Boursin ail et fine herbe", None, "fromage frais"),
        ("250 g de pruneaux dénoyautés", "g", "pruneaux"),
        ("1 chèvres bûche", None, "fromage de chèvre"),
    ],
)
def test_real_world_lines_are_matched_to_the_right_ingredient(index, line, unit, canonical):
    parsed = parse_line(line)
    names = {i: e["name"] for i, e in enumerate(parse_catalog())}

    match = index.find(parsed.name)

    assert (parsed.unit.code if parsed.unit else None) == unit
    assert match is not None and names[match.ingredient_id] == canonical


def test_leftmost_entry_wins_when_two_have_the_same_length(index):
    names = {i: e["name"] for i, e in enumerate(parse_catalog())}

    assert names[index.find("boursin ail").ingredient_id] == "fromage frais"
    assert names[index.find("ail boursin").ingredient_id] == "ail"
