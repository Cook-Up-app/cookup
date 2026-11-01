"""Saisie des allergies : reconnaissance flexible, familles d'aliments, effet sur le moteur."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.catalog.models import Ingredient
from apps.core.lexicon import FOOD_GROUPS
from apps.core.reference import Allergen, FoodGroup
from apps.households import restrictions
from apps.households.models import Diner, DinerRestriction, Membership
from apps.planner import loading
from apps.planner.engine import rules
from tests.planner import builders

Kind = restrictions.Kind


def _nothing(_: str) -> str | None:
    return None


def _catalog(term: str) -> str | None:
    return "lentilles" if restrictions.word_set(term) == {"lentille"} else None


@pytest.mark.parametrize(
    "typed", ["légumineuse", "Légumineuses", "LEGUMINEUSES", "  légumineuses ", "légumes secs"]
)
def test_a_food_group_is_recognised_in_any_form(typed):
    target = restrictions.recognise(typed, _nothing)

    assert (target.kind, target.value) == (Kind.GROUP, FoodGroup.LEGUMES_PULSES.value)


@pytest.mark.parametrize(
    ("typed", "allergen"),
    [
        ("arachides", Allergen.PEANUTS),
        ("Cacahuète", Allergen.PEANUTS),
        ("oeufs", Allergen.EGGS),
        ("œuf", Allergen.EGGS),
        ("lactose", Allergen.MILK),
        ("amandes", Allergen.TREE_NUTS),
        ("Céréales contenant du gluten", Allergen.GLUTEN),
        ("crevettes", Allergen.CRUSTACEANS),
    ],
)
def test_official_allergens_and_their_common_names_are_recognised(typed, allergen):
    target = restrictions.recognise(typed, _nothing)

    assert (target.kind, target.value) == (Kind.ALLERGEN, allergen.value)


def test_a_catalog_ingredient_is_matched_singular_or_plural():
    for typed in ("lentille", "lentilles", "Lentilles "):
        assert restrictions.recognise(typed, _catalog).kind is Kind.INGREDIENT


def test_an_unknown_word_is_kept_as_free_text_and_flagged():
    target = restrictions.recognise("kiwi", _nothing)

    assert target.kind is Kind.FREE and not target.known
    assert "n'est pas dans notre catalogue" in restrictions.describe(target)


def test_a_broader_match_is_explained_to_the_user():
    text = restrictions.describe(restrictions.recognise("amande", _nothing))

    assert "Fruits à coque" in text and "par prudence" in text


def test_terms_are_split_cleaned_and_deduplicated():
    terms = restrictions.split_terms("kiwi, Kiwis ;  noix  de  pécan\n, ,")

    assert terms == ["kiwi", "noix de pécan"]


def test_terms_are_bounded():
    many = ",".join(f"mot{i}" for i in range(50))

    assert len(restrictions.split_terms(many)) == restrictions.MAX_TERMS
    assert len(restrictions.split_terms("x" * 1000)[0]) == restrictions.MAX_TERM_LENGTH


def test_every_group_member_has_words_and_every_group_is_defined():
    assert set(FOOD_GROUPS) == set(FoodGroup)
    for group in FoodGroup:
        coverage = restrictions.group_coverage(group.value)
        assert coverage.word_sets and all(coverage.word_sets)


def test_pulses_cover_every_common_legume_in_recipe_text():
    coverage = restrictions.group_coverage(FoodGroup.LEGUMES_PULSES.value)
    texts = ["lentilles corail", "pois chiches", "haricots rouges", "petits pois", "fèves", "soja"]

    for text in texts:
        words = loading.recipe_words([text])
        assert any(ws <= words for ws in coverage.word_sets), text
    assert Allergen.PEANUTS in coverage.allergens


def _strict_context(restriction_words):
    return builders.context(diners=[builders.diner(strict_word_sets=restriction_words)])


def test_the_engine_refuses_a_recipe_containing_any_member_of_the_group():
    coverage = restrictions.group_coverage(FoodGroup.LEGUMES_PULSES.value)
    ctx = _strict_context(coverage.word_sets)
    slot = builders.slots(days=1)[0]
    unsafe = builders.recipe(words=loading.recipe_words(["200 g de lentilles vertes"]))
    safe = builders.recipe(words=loading.recipe_words(["200 g de riz"]))

    assert not rules.is_allowed(unsafe, slot, ctx)
    assert rules.is_allowed(safe, slot, ctx)


@pytest.fixture
def lea(owner_client):
    return Diner.objects.create(household=Membership.objects.get().household, first_name="Léa")


def _add(client, diner, **data):
    return client.post(reverse("households:restriction-add", args=[diner.pk]), data)


@pytest.mark.django_db
def test_several_targets_are_saved_in_one_submission(owner_client, lea):
    Ingredient.objects.create(name="lentilles", normalized_name="lentille")

    response = _add(
        owner_client, lea,
        severity="strict_allergy", allergens=["milk", "eggs"], groups=["citrus"],
        other="Légumineuses, lentille, kiwis",
    )  # fmt: skip

    assert response.status_code == 302
    saved = DinerRestriction.objects.filter(diner=lea)
    assert set(saved.exclude(allergen="").values_list("allergen", flat=True)) == {"milk", "eggs"}
    assert set(saved.exclude(food_group="").values_list("food_group", flat=True)) == {
        "citrus", "pulses",
    }  # fmt: skip
    assert saved.filter(ingredient_name__iexact="kiwis").exists()
    assert saved.filter(ingredient_name="lentilles").exists()


@pytest.mark.django_db
def test_the_user_is_told_what_was_understood(owner_client, lea):
    response = _add(owner_client, lea, severity="avoid", other="légumineuse, kiwi")
    texts = [str(m) for m in get_messages(response.wsgi_request)]

    assert any("Légumineuses : exclut" in t for t in texts)
    assert any("n'est pas dans notre catalogue" in t for t in texts)


@pytest.mark.django_db
def test_adding_twice_does_not_duplicate_and_updates_the_severity(owner_client, lea):
    _add(owner_client, lea, severity="avoid", allergens=["milk"])
    _add(owner_client, lea, severity="strict_allergy", allergens=["milk"], other="LEGUMINEUSES")
    _add(owner_client, lea, severity="strict_allergy", other="légumineuse")

    assert DinerRestriction.objects.filter(diner=lea, allergen="milk").count() == 1
    assert DinerRestriction.objects.get(diner=lea, allergen="milk").severity == "strict_allergy"
    assert DinerRestriction.objects.filter(diner=lea, food_group="pulses").count() == 1


@pytest.mark.django_db
def test_an_empty_submission_is_refused_with_a_clear_message(owner_client, lea):
    response = _add(owner_client, lea, severity="strict_allergy")

    assert response.status_code == 200
    assert "Cochez au moins une case" in response.content.decode()
    assert not DinerRestriction.objects.exists()


@pytest.mark.django_db
def test_invalid_input_is_refused_before_saving(owner_client, lea):
    _add(owner_client, lea, severity="nonsense", allergens=["milk"])
    _add(owner_client, lea, severity="avoid", allergens=["not-an-allergen"])
    _add(owner_client, lea, severity="avoid", groups=["nope"])

    assert not DinerRestriction.objects.exists()


@pytest.mark.django_db
def test_a_member_cannot_add_restrictions(client, owner, lea):
    from apps.households.models import Membership as M
    from tests.conftest import make_user

    member = make_user("member@example.com", mfa=False)
    M.objects.create(user=member, household=lea.household)
    client.force_login(member)

    response = _add(client, lea, severity="avoid", allergens=["milk"])

    assert response.status_code == 404 and not DinerRestriction.objects.exists()


@pytest.mark.django_db
def test_a_restriction_needs_at_least_one_target(lea):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        DinerRestriction.objects.create(diner=lea)


@pytest.mark.django_db
def test_strict_group_and_ingredient_reach_the_engine_and_avoid_lowers_taste(owner, lea):
    lentils = Ingredient.objects.create(name="lentilles", normalized_name="lentille")
    cream = Ingredient.objects.create(name="crème", normalized_name="creme")
    household = lea.household
    DinerRestriction.objects.create(diner=lea, food_group="pulses", severity="strict_allergy")
    DinerRestriction.objects.create(diner=lea, ingredient_name="kiwi", severity="strict_allergy")
    DinerRestriction.objects.create(diner=lea, ingredient_name="crème", severity="avoid")

    view = loading.load_diners(household)[0]

    assert frozenset({"lentille"}) in view.strict_word_sets
    assert frozenset({"kiwi"}) in view.strict_word_sets
    assert Allergen.PEANUTS in view.strict_allergens
    assert view.taste[cream.pk] == loading.AVOID_SCORE
    assert lentils.pk not in view.taste  # la famille est stricte : règle dure, pas un goût


@pytest.mark.django_db
def test_non_strict_group_lowers_the_taste_of_its_catalog_members(owner, lea):
    lentils = Ingredient.objects.create(name="lentilles", normalized_name="lentille")
    DinerRestriction.objects.create(diner=lea, food_group="pulses", severity="intolerance")

    view = loading.load_diners(lea.household)[0]

    assert view.taste[lentils.pk] == loading.AVOID_SCORE
    assert not view.strict_word_sets


@pytest.mark.django_db
def test_diner_page_shows_what_a_group_excludes(owner_client, lea):
    DinerRestriction.objects.create(diner=lea, food_group="pulses", severity="strict_allergy")
    DinerRestriction.objects.create(diner=lea, ingredient_name="kiwi", severity="avoid")

    page = owner_client.get(reverse("households:diner", args=[lea.pk])).content.decode()

    assert "Légumineuses" in page and "Exclut : lentille" in page
    assert "Texte libre" in page
