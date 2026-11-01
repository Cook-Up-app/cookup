"""Styles de cuisine du foyer : formulaire, déduction depuis les recettes, effet sur le score."""

import pytest
from django.urls import reverse

from apps.catalog import cuisine
from apps.core.reference import Cuisine
from apps.households.models import HouseholdSettings, Membership
from apps.planner.engine.criteria import NEUTRAL, PlanState, total_score
from apps.planner.engine.rules import is_allowed
from apps.planner.engine.style import StyleCriterion
from tests.planner import builders


def _score(recipe, **settings):
    ctx = builders.context(**settings)
    return StyleCriterion().score(recipe, builders.slots(days=1)[0], ctx, PlanState())


def test_no_preference_is_neutral():
    assert _score(builders.recipe()) == NEUTRAL
    assert _score(builders.recipe(cuisine="italian")) == NEUTRAL  # cuisine sans préférence


def test_liked_beats_neutral_beats_avoided():
    recipe = builders.recipe(cuisine="italian")

    liked = _score(recipe, liked_cuisines=frozenset({"italian"}))
    avoided = _score(recipe, avoided_cuisines=frozenset({"italian"}))

    assert liked > _score(builders.recipe(cuisine="french")) > avoided


def test_spice_above_the_tolerance_lowers_the_score():
    hot = builders.recipe(spice=3)

    assert _score(hot, spice_tolerance=0) < _score(hot, spice_tolerance=3)
    assert _score(hot, spice_tolerance=0) < NEUTRAL


def test_exoticism_slider_pushes_distant_cuisines_up_or_down():
    asian = builders.recipe(cuisine="asian", exotic=True)

    assert _score(asian, exoticism=0) < _score(asian, exoticism=1) < _score(asian, exoticism=2)


def test_styles_never_exclude_a_recipe():
    recipe = builders.recipe(cuisine="indian", spice=3, exotic=True)
    ctx = builders.context(avoided_cuisines=frozenset({"indian"}), spice_tolerance=0, exoticism=0)

    assert is_allowed(recipe, builders.slots(days=1)[0], ctx)


def test_liked_cuisine_ranks_a_recipe_higher_in_the_total_score():
    slot = builders.slots(days=1)[0]
    recipe = builders.recipe(cuisine="italian")
    plain = builders.context()
    fan = builders.context(liked_cuisines=frozenset({"italian"}))

    assert total_score(recipe, slot, fan, PlanState()) > total_score(
        recipe, slot, plain, PlanState()
    )


def test_a_liked_cuisine_is_cited_in_the_explanation():
    ctx = builders.context(
        liked_cuisines=frozenset({"italian"}), cuisine_labels={"italian": "Italienne"}
    )

    text = StyleCriterion().explain(
        builders.recipe(cuisine="italian"), builders.slots(days=1)[0], ctx, PlanState()
    )

    assert text == "cuisine italienne appréciée"


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Lasagnes à la bolognaise", "pâtes", "parmesan"], "italian"),
        (["Poulet curry", "curcuma", "lait de coco"], "indian"),
        (["Couscous royal", "semoule", "harissa", "merguez"], "oriental"),
        (["Wok de nouilles", "sauce soja", "gingembre"], "asian"),
        (["Tacos", "tortillas", "guacamole"], "mexican"),
        (["Gratin dauphinois", "gruyère"], "french"),
        (["Salade verte"], ""),
    ],
)
def test_cuisine_is_inferred_from_title_and_ingredients(texts, expected):
    assert cuisine.infer_cuisine(frozenset(), texts) == expected


def test_a_cuisine_tag_wins_over_inference():
    tags = frozenset({"cuisine:mexican"})

    assert cuisine.infer_cuisine(tags, ["lasagnes", "parmesan"]) == "mexican"
    assert cuisine.infer_cuisine(frozenset({"cuisine:nonsense"}), ["lasagnes"]) == "italian"


def test_spice_level_and_exotic_flag():
    assert cuisine.spice_level(frozenset(), ["piment d'Espelette"]) == cuisine.HOT
    assert cuisine.spice_level(frozenset(), ["curry"]) == cuisine.MEDIUM
    assert cuisine.spice_level(frozenset({"épicé"}), ["riz"]) == cuisine.MEDIUM
    assert cuisine.spice_level(frozenset(), ["riz", "poulet"]) == 0
    assert cuisine.is_exotic("asian") and not cuisine.is_exotic("french")
    assert not cuisine.is_exotic("")


@pytest.mark.django_db
def test_owner_saves_styles_and_they_reach_the_engine(owner_client):
    response = owner_client.post(
        reverse("households:styles"),
        {
            "liked_cuisines": ["italian", "french"], "avoided_cuisines": ["indian"],
            "spice_tolerance": "2", "exoticism": "0",
        },
    )  # fmt: skip

    assert response.status_code == 302
    saved = HouseholdSettings.objects.get(household=Membership.objects.get().household)
    assert saved.liked_cuisines == ["italian", "french"]
    assert saved.avoided_cuisines == ["indian"]
    assert (saved.spice_tolerance, saved.exoticism) == (2, 0)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        {"liked_cuisines": ["italian"], "avoided_cuisines": ["italian"]},
        {"liked_cuisines": ["klingon"]},
        {"spice_tolerance": "9"},
        {"exoticism": "-1"},
    ],
)
def test_invalid_styles_are_refused(owner_client, data):
    base = {"spice_tolerance": "1", "exoticism": "1"}

    response = owner_client.post(reverse("households:styles"), {**base, **data})

    assert response.status_code == 200
    assert not HouseholdSettings.objects.filter(liked_cuisines__contains=["klingon"]).exists()


@pytest.mark.django_db
def test_a_member_can_read_but_not_change_the_styles(client, owner):
    from tests.conftest import make_user

    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=Membership.objects.get(user=owner).household)
    client.force_login(member)

    assert client.get(reverse("households:styles")).status_code == 200
    client.post(
        reverse("households:styles"),
        {"liked_cuisines": ["italian"], "spice_tolerance": "1", "exoticism": "1"},
    )

    assert not HouseholdSettings.objects.filter(liked_cuisines__contains=["italian"]).exists()


@pytest.mark.django_db
def test_the_styles_page_is_not_public(client):
    assert client.get(reverse("households:styles"))["Location"].startswith(reverse("account_login"))


def test_every_cuisine_has_a_detection_vocabulary():
    assert set(cuisine.CUISINE_WORDS) == set(Cuisine)
