import pytest
from django.urls import reverse

from apps.catalog.models import Ingredient, Recipe, RecipeFeedback
from apps.households.models import Diner, HouseholdEquipment, Membership, TastePreference
from apps.planner import loading, services
from apps.planner.engine import History, generate
from apps.planner.learning import learn_tastes
from tests.conftest import make_user, seed_catalog
from tests.planner.builders import context, diner, recipe, slots


def test_nothing_is_learned_without_ratings():
    assert learn_tastes({}, {}) == {}
    assert learn_tastes({"unknown": 5}, {"other": frozenset({1})}) == {}


def test_loved_ingredients_rise_and_disliked_ones_fall():
    ratings = {"a": 5, "b": 5, "c": 1, "d": 1}
    ingredients = {
        "a": frozenset({1, 9}),
        "b": frozenset({1, 9}),
        "c": frozenset({2, 9}),
        "d": frozenset({2, 9}),
    }

    learned = learn_tastes(ratings, ingredients)

    assert learned[1] > 0 > learned[2]
    assert abs(learned.get(9, 0)) < 0.01  # présent partout : aucune préférence


def test_a_household_that_rates_everything_high_learns_relative_preferences_only():
    ratings = {"a": 5, "b": 5, "c": 4, "d": 4}
    ingredients = {
        "a": frozenset({1}),
        "b": frozenset({1}),
        "c": frozenset({2}),
        "d": frozenset({2}),
    }

    learned = learn_tastes(ratings, ingredients)

    assert learned[1] > learned.get(2, 0.0) and learned.get(2, 0.0) < 0.5


def test_few_ratings_give_cautious_conclusions():
    one = learn_tastes({"a": 5}, {"a": frozenset({1})})[1]
    many = learn_tastes(
        {f"r{i}": 5 for i in range(10)} | {"z": 1},
        {f"r{i}": frozenset({1}) for i in range(10)} | {"z": frozenset({2})},
    )[1]

    assert 0 < one < many <= 2


def test_values_stay_on_the_taste_scale():
    ratings = {f"r{i}": 5 for i in range(50)} | {f"s{i}": 1 for i in range(50)}
    ingredients = {f"r{i}": frozenset({1}) for i in range(50)} | {
        f"s{i}": frozenset({2}) for i in range(50)
    }

    assert all(-2 <= value <= 2 for value in learn_tastes(ratings, ingredients).values())


def test_learned_taste_steers_the_menu_like_a_typed_taste():
    liked, disliked = (
        recipe(ingredient_ids=frozenset({1000})),
        recipe(ingredient_ids=frozenset({2000})),
    )
    learned = learn_tastes(
        {"x": 5, "y": 5, "z": 1},
        {"x": frozenset({1000}), "y": frozenset({1000}), "z": frozenset({2000})},
    )
    ctx = context([diner(taste=learned)])

    picks = [
        generate(slots(1, ("lunch",)), [liked, disliked], ctx, seed=s).assignments[0].recipe_id
        for s in range(40)
    ]

    assert picks.count(liked.id) > picks.count(disliked.id) * 2


def test_ratings_steer_the_selection_through_the_rating_criterion():
    good, bad = recipe(), recipe()
    ctx = context(history=History(ratings={good.id: 5, bad.id: 1}))

    picks = [
        generate(slots(1, ("lunch",)), [good, bad], ctx, seed=s).assignments[0].recipe_id
        for s in range(40)
    ]

    assert picks.count(good.id) > 25


@pytest.fixture
def home(owner, db):
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    for code in ("hob", "oven"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    Diner.objects.create(household=household, first_name="Léa")
    return household


def rate(household, titles, score):
    for recipe_ in Recipe.objects.filter(title__in=titles):
        RecipeFeedback.objects.update_or_create(
            household=household, recipe=recipe_, defaults={"rating": score}
        )


def test_ratings_become_tastes_for_the_engine(home):
    rate(home, ["Curry de pois chiches", "Dahl de lentilles corail"], 5)
    rate(home, ["Velouté de champignons", "Risotto aux champignons"], 1)

    view = loading.load_diners(home)[0]
    chickpeas = Ingredient.objects.get(name="pois chiches").pk
    mushrooms = Ingredient.objects.get(name="champignon").pk

    assert view.taste[chickpeas] > 0 > view.taste[mushrooms]


def test_typed_tastes_override_what_was_learned(home):
    rate(home, ["Velouté de champignons", "Risotto aux champignons"], 1)
    mushrooms = Ingredient.objects.get(name="champignon")
    TastePreference.objects.create(diner=home.diners.get(), ingredient=mushrooms, score=2)

    assert loading.load_diners(home)[0].taste[mushrooms.pk] == 2


def test_other_households_ratings_do_not_leak(home, other_owner):
    other = Membership.objects.get(user=other_owner).household
    rate(other, ["Velouté de champignons"], 1)

    assert loading.load_learned_tastes(home) == {}


def test_next_menus_follow_the_ratings(home):
    """Critère M6 : les notes modifient les menus suivants."""
    from datetime import date

    def mushroom_meals(seed_base):
        total = 0
        for seed in range(seed_base, seed_base + 12):
            plan = services.create_plan(
                home,
                services.PlanRequest(
                    start_date=date(2027, 1, 4),
                    end_date=date(2027, 1, 6),
                    meals=("lunch", "dinner"),
                    diner_ids=tuple(str(d.pk) for d in home.diners.all()),
                ),
                date(2027, 1, 4),
                seed=seed,
            )
            total += sum(
                "champignon" in s.recipe.search_text for s in plan.slots.select_related("recipe")
            )
            plan.delete()
        return total

    before = mushroom_meals(0)
    rate(home, [r.title for r in Recipe.objects.filter(search_text__contains="champignon")], 1)
    after = mushroom_meals(0)

    assert after < before


def test_feedback_form_saves_the_household_opinion(owner_client, home):
    gratin = Recipe.objects.get(title="Gratin de courgettes")

    owner_client.post(
        reverse("catalog:feedback", args=[gratin.pk]), {"rating": "4", "favorite": "on"}
    )

    feedback = RecipeFeedback.objects.get(household=home, recipe=gratin)
    assert (feedback.rating, feedback.favorite, feedback.excluded) == (4, True, False)
    page = owner_client.get(reverse("catalog:detail", args=[gratin.pk])).content.decode()
    assert 'value="4" selected' in page.replace("\n", " ") and "Votre avis" in page


def test_feedback_can_be_changed_and_cleared(owner_client, home):
    gratin = Recipe.objects.get(title="Gratin de courgettes")
    url = reverse("catalog:feedback", args=[gratin.pk])

    owner_client.post(url, {"rating": "5"})
    owner_client.post(url, {"rating": "", "excluded": "on"})

    feedback = RecipeFeedback.objects.get()
    assert feedback.rating is None and feedback.excluded and RecipeFeedback.objects.count() == 1


def test_favorite_and_excluded_together_are_refused(owner_client, home):
    gratin = Recipe.objects.get(title="Gratin de courgettes")

    owner_client.post(
        reverse("catalog:feedback", args=[gratin.pk]), {"favorite": "on", "excluded": "on"}
    )

    assert not RecipeFeedback.objects.exists()


@pytest.mark.parametrize("rating", ["0", "6", "abc", "-1"])
def test_out_of_range_ratings_are_refused(owner_client, home, rating):
    gratin = Recipe.objects.get(title="Gratin de courgettes")

    owner_client.post(reverse("catalog:feedback", args=[gratin.pk]), {"rating": rating})

    assert not RecipeFeedback.objects.exists()


def test_excluded_recipes_leave_the_next_menus(owner_client, home):
    from datetime import date

    excluded = Recipe.objects.get(title="Gratin de courgettes")
    owner_client.post(reverse("catalog:feedback", args=[excluded.pk]), {"excluded": "on"})

    for seed in range(10):
        plan = services.create_plan(
            home,
            services.PlanRequest(
                start_date=date(2027, 1, 4),
                end_date=date(2027, 1, 6),
                meals=("lunch", "dinner"),
                diner_ids=tuple(str(d.pk) for d in home.diners.all()),
            ),
            date(2027, 1, 4),
            seed=seed,
        )
        assert excluded.pk not in [s.recipe_id for s in plan.slots.all()]
        plan.delete()


def test_feedback_is_scoped_to_the_household_and_needs_a_post(
    owner_client, home, other_owner, client
):
    gratin = Recipe.objects.get(title="Gratin de courgettes")
    other = Membership.objects.get(user=other_owner).household
    RecipeFeedback.objects.create(household=other, recipe=gratin, rating=1)

    owner_client.post(reverse("catalog:feedback", args=[gratin.pk]), {"rating": "5"})

    assert RecipeFeedback.objects.get(household=other).rating == 1
    assert RecipeFeedback.objects.get(household=home).rating == 5
    assert owner_client.get(reverse("catalog:feedback", args=[gratin.pk])).status_code == 405
    assert (
        client.post(reverse("catalog:feedback", args=[gratin.pk]), {"rating": "5"}).status_code
        == 302
    )


def test_simple_member_can_rate(client, home):
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=home)
    client.force_login(member)
    gratin = Recipe.objects.get(title="Gratin de courgettes")

    client.post(reverse("catalog:feedback", args=[gratin.pk]), {"rating": "3"})

    assert RecipeFeedback.objects.get(household=home).rating == 3
