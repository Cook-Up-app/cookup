import re
import uuid

import pytest
from django.urls import reverse

from apps.core.reference import Allergen
from apps.households import services as household_services
from apps.households.models import (
    Diner,
    DinerRestriction,
    HouseholdEquipment,
    HouseholdSettings,
    Membership,
    TastePreference,
)
from apps.onboarding import services, steps
from tests.conftest import make_user, seed_catalog

STRICT = DinerRestriction.Severity.STRICT_ALLERGY


@pytest.fixture
def fresh(client, db):
    """Propriétaire tout neuf : un foyer vide, créé automatiquement à la première visite."""
    user = make_user("fresh@example.com")
    household_services.create_household(user, "Mon foyer")
    client.force_login(user)
    return client, user


def household_of(user):
    return Membership.objects.get(user=user).household


def step_url(slug, key=None):
    return reverse("onboarding:step", args=[slug, key] if key else [slug])


def test_a_brand_new_owner_lands_in_the_assistant(fresh):
    client, _ = fresh

    response = client.get(reverse("core:home"))

    assert response.status_code == 302 and response["Location"] == reverse("onboarding:start")
    assert client.get(reverse("onboarding:start"))["Location"] == step_url("foyer")


def test_a_household_already_in_use_is_never_sent_back(client, owner):
    household = household_of(owner)
    Diner.objects.create(household=household, first_name="Léa")
    client.force_login(owner)

    assert client.get(reverse("core:home")).status_code == 200


@pytest.mark.parametrize("model_setup", ["equipment", "plan", "feedback"])
def test_any_trace_of_use_disables_the_assistant_redirect(owner, model_setup):
    from datetime import date

    from apps.catalog.models import Recipe, RecipeFeedback
    from apps.planner.models import MenuPlan

    household = household_of(owner)
    if model_setup == "equipment":
        HouseholdEquipment.objects.create(household=household, equipment_id="oven")
    elif model_setup == "plan":
        MenuPlan.objects.create(
            household=household, start_date=date.today(), end_date=date.today(), seed=1
        )
    else:
        seed_catalog()
        RecipeFeedback.objects.create(household=household, recipe=Recipe.objects.first(), rating=4)

    assert services.needs_onboarding(household) is False


def test_simple_members_skip_the_assistant(client, owner):
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=household_of(owner))
    client.force_login(member)

    assert client.get(reverse("core:home")).status_code == 200
    assert client.get(step_url("foyer"))["Location"] == reverse("core:home")


def test_the_first_question_renames_the_household(fresh):
    client, user = fresh

    response = client.post(step_url("foyer"), {"name": "Chez les Dupont", "action": "save"})

    assert response["Location"] == step_url("portions")
    assert household_of(user).name == "Chez les Dupont"


def test_empty_name_is_refused_with_an_error(fresh):
    client, user = fresh
    before = household_of(user).name

    response = client.post(step_url("foyer"), {"name": "", "action": "save"})

    assert response.status_code == 200 and household_of(user).name == before


def test_servings_are_saved_and_invalid_choices_refused(fresh):
    client, user = fresh

    client.post(step_url("portions"), {"servings": "6", "action": "save"})
    bad = client.post(step_url("portions"), {"servings": "99", "action": "save"})

    assert household_of(user).default_servings == 6 and bad.status_code == 200


def test_skipping_saves_nothing_and_moves_on(fresh):
    client, user = fresh

    response = client.post(step_url("portions"), {"servings": "7", "action": "skip"})

    assert response["Location"] == step_url("convives") and household_of(user).default_servings == 4


def test_diners_can_be_added_and_removed_on_the_same_screen(fresh):
    client, user = fresh
    household = household_of(user)

    added = client.post(
        step_url("convives"), {"first_name": "Léa", "age_group": "child", "action": "add"}
    )
    client.post(step_url("convives"), {"first_name": "Tom", "age_group": "adult", "action": "add"})
    lea = Diner.objects.get(first_name="Léa")
    client.post(step_url("convives"), {"diner": str(lea.pk), "action": "remove"})

    assert added["Location"] == step_url("convives")
    assert list(Diner.objects.filter(household=household).values_list("first_name", flat=True)) == [
        "Tom"
    ]
    page = client.get(step_url("convives")).content.decode()
    assert 'row-title">Tom' in page and 'row-title">Léa' not in page


def test_removing_a_foreign_diner_is_refused(fresh, other_owner):
    client, _ = fresh
    foreign = Diner.objects.create(household=household_of(other_owner), first_name="Secret")

    response = client.post(step_url("convives"), {"diner": str(foreign.pk), "action": "remove"})

    assert response.status_code == 404 and Diner.objects.filter(pk=foreign.pk).exists()


def test_per_diner_steps_appear_for_each_person(fresh):
    client, user = fresh
    for name in ("Léa", "Tom"):
        Diner.objects.create(household=household_of(user), first_name=name)

    sequence = steps.sequence(household_of(user))

    slugs = [ref.slug for ref in sequence]
    assert slugs.count("allergies") == slugs.count("regimes") == slugs.count("gouts") == 2
    assert slugs[0] == "foyer" and slugs[-1] == "fin"
    assert slugs.index("convives") < slugs.index("allergies") < slugs.index("equipements")


def test_allergies_become_strict_restrictions_and_can_be_changed(fresh):
    client, user = fresh
    lea = Diner.objects.create(household=household_of(user), first_name="Léa")
    DinerRestriction.objects.create(diner=lea, ingredient_name="kiwi", severity="avoid")

    client.post(
        step_url("allergies", lea.pk), {"allergens": ["tree_nuts", "milk"], "action": "save"}
    )
    client.post(step_url("allergies", lea.pk), {"allergens": ["milk"], "action": "save"})

    strict = set(lea.restrictions.filter(severity=STRICT).values_list("allergen", flat=True))
    assert strict == {Allergen.MILK}
    assert lea.restrictions.filter(ingredient_name="kiwi").exists()  # le reste est conservé


def test_unknown_allergens_are_refused(fresh):
    client, user = fresh
    lea = Diner.objects.create(household=household_of(user), first_name="Léa")

    client.post(step_url("allergies", lea.pk), {"allergens": ["pizza"], "action": "save"})

    assert not lea.restrictions.exists()


def test_diets_equipment_meals_times_budget_and_leftovers_are_saved(fresh):
    client, user = fresh
    household = household_of(user)
    lea = Diner.objects.create(household=household, first_name="Léa")

    client.post(step_url("regimes", lea.pk), {"diets": ["vegetarian"], "action": "save"})
    client.post(
        step_url("equipements"), {"equipment": ["oven", "cookeo_yy5449fb"], "action": "save"}
    )
    client.post(step_url("repas"), {"meals": ["breakfast", "dinner"], "action": "save"})
    client.post(step_url("temps-semaine"), {"minutes": "30", "action": "save"})
    client.post(step_url("temps-weekend"), {"minutes": "120", "action": "save"})
    client.post(step_url("budget"), {"budget": "3", "action": "save"})
    client.post(step_url("restes"), {"days": ["0", "6"], "action": "save"})

    lea.refresh_from_db()
    settings = HouseholdSettings.objects.get(household=household)
    assert lea.diets == ["vegetarian"]
    assert set(HouseholdEquipment.objects.values_list("equipment_id", flat=True)) == {
        "oven",
        "cookeo_yy5449fb",
    }
    assert settings.meals == ["breakfast", "dinner"]
    assert (settings.max_minutes_weekday, settings.max_minutes_weekend, settings.budget_level) == (
        30,
        120,
        3,
    )
    assert settings.leftover_weekdays == [0, 6]


def test_the_meals_question_needs_at_least_one_answer(fresh):
    client, user = fresh

    response = client.post(step_url("repas"), {"action": "save"})

    assert (
        response.status_code == 200
        and not HouseholdSettings.objects.filter(household=household_of(user), meals=[]).exists()
    )


def test_tastes_use_three_states_and_neutral_clears(fresh):
    from apps.catalog.models import Ingredient

    seed_catalog()
    client, user = fresh
    lea = Diner.objects.create(household=household_of(user), first_name="Léa")
    chicken, carrot = Ingredient.objects.get(name="poulet"), Ingredient.objects.get(name="carotte")

    client.post(
        step_url("gouts", lea.pk), {f"i{chicken.pk}": "1", f"i{carrot.pk}": "-1", "action": "save"}
    )
    after_first = dict(TastePreference.objects.values_list("ingredient_id", "score"))
    client.post(
        step_url("gouts", lea.pk), {f"i{chicken.pk}": "0", f"i{carrot.pk}": "-1", "action": "save"}
    )

    assert after_first == {chicken.pk: 2, carrot.pk: -2}
    assert dict(TastePreference.objects.values_list("ingredient_id", "score")) == {carrot.pk: -2}


def test_saved_answers_come_back_when_the_step_is_reopened(fresh):
    client, user = fresh
    client.post(step_url("temps-semaine"), {"minutes": "60", "action": "save"})

    page = client.get(step_url("temps-semaine")).content.decode()

    assert re.search(r'<input[^>]*value="60"[^>]*checked', page)


def test_other_households_diners_are_not_reachable_in_the_assistant(fresh, other_owner):
    client, _ = fresh
    foreign = Diner.objects.create(household=household_of(other_owner), first_name="Secret")

    assert client.get(step_url("allergies", foreign.pk)).status_code == 404
    assert (
        client.post(
            step_url("allergies", foreign.pk), {"allergens": ["milk"], "action": "save"}
        ).status_code
        == 404
    )
    assert not foreign.restrictions.exists()


def test_unknown_steps_and_mismatched_keys_are_not_found(fresh):
    client, _ = fresh

    assert client.get(step_url("inconnue")).status_code == 404
    assert client.get(step_url("allergies", uuid.uuid4())).status_code == 404
    assert client.get(step_url("foyer", uuid.uuid4())).status_code == 404


def test_progress_and_navigation_on_each_screen(fresh):
    client, user = fresh
    Diner.objects.create(household=household_of(user), first_name="Léa")

    first = client.get(step_url("foyer")).content.decode()
    middle = client.get(step_url("equipements")).content.decode()
    total = len(steps.sequence(household_of(user)))

    assert f'max="{total}"' in first and 'value="1"' in first
    assert "Retour" not in first and "Retour" in middle and "Passer l'assistant" in middle
    assert "<progress" in middle and 'aria-label="Progression de l\'assistant"' in middle


def test_finishing_marks_the_household_and_opens_the_next_destination(fresh):
    client, user = fresh

    to_menu = client.post(step_url("fin"), {"action": "menu"})

    assert to_menu["Location"] == reverse("planner:new")
    assert HouseholdSettings.objects.get(household=household_of(user)).onboarded_at is not None
    assert client.get(reverse("core:home")).status_code == 200


def test_the_summary_lists_what_was_configured(fresh):
    client, user = fresh
    lea = Diner.objects.create(household=household_of(user), first_name="Léa")
    DinerRestriction.objects.create(diner=lea, allergen="tree_nuts", severity=STRICT)
    HouseholdEquipment.objects.create(household=household_of(user), equipment_id="oven")

    page = client.get(step_url("fin")).content.decode()

    assert "Léa" in page and "Fruits à coque" in page and "Four" in page


def test_dismissing_the_assistant_loses_nothing(fresh):
    client, user = fresh
    client.post(step_url("portions"), {"servings": "5", "action": "save"})

    response = client.post(reverse("onboarding:dismiss"))

    assert response["Location"] == reverse("core:home") and household_of(user).default_servings == 5
    assert client.get(reverse("core:home")).status_code == 200


def test_the_assistant_requires_a_session_and_a_post_for_actions(client, db, fresh):
    assert client.get(step_url("foyer")).status_code == 200  # fresh est connecté
    anonymous = type(client)()
    assert anonymous.get(step_url("foyer")).status_code == 302
    assert client.get(reverse("onboarding:dismiss")).status_code == 405


def test_staff_without_mfa_is_sent_to_enrolment_before_the_assistant(client, db):
    user = make_user("nomfa@example.com", mfa=False)
    user.is_staff = True
    user.save()
    client.force_login(user)

    response = client.get(step_url("foyer"))

    assert response["Location"].startswith(reverse("mfa_index"))


def test_step_pages_have_no_inline_script_and_a_single_h1(fresh):
    client, _ = fresh

    page = client.get(step_url("budget")).content.decode()

    assert page.count("<h1") == 1 and not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page)


def test_the_allergy_step_accepts_families_and_free_text(fresh):
    client, user = fresh
    lea = Diner.objects.create(household=household_of(user), first_name="Léa")

    client.post(
        step_url("allergies", lea.pk),
        {"allergens": ["milk"], "groups": ["pulses"], "other": "kiwis", "action": "save"},
    )
    client.post(
        step_url("allergies", lea.pk), {"allergens": ["milk"], "groups": [], "action": "save"}
    )

    strict = lea.restrictions.filter(severity=STRICT)
    assert strict.filter(allergen="milk").exists()
    assert not strict.filter(food_group="pulses").exists()  # décoché : retiré
    assert strict.filter(ingredient_name="kiwis").exists()  # le texte libre est conservé


def test_the_styles_step_saves_cuisines_and_levels(fresh):
    client, user = fresh

    client.post(
        step_url("styles"),
        {
            "liked_cuisines": ["italian"], "avoided_cuisines": ["indian"],
            "spice_tolerance": "0", "exoticism": "2", "action": "save",
        },
    )  # fmt: skip

    settings = HouseholdSettings.objects.get(household=household_of(user))
    assert settings.liked_cuisines == ["italian"] and settings.avoided_cuisines == ["indian"]
    assert (settings.spice_tolerance, settings.exoticism) == (0, 2)
