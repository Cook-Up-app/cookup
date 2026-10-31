import re

import pytest
from django.urls import reverse

from apps.catalog.models import Recipe
from tests.conftest import seed_catalog

INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)


@pytest.fixture
def gratin(db):
    seed_catalog()
    return Recipe.objects.get(title="Gratin dauphinois au Cookeo")


def test_kitchen_mode_requires_a_session(client, gratin):
    assert client.get(reverse("catalog:kitchen", args=[gratin.pk])).status_code == 302


def test_steps_are_rendered_one_per_item_for_the_script(owner_client, gratin):
    page = owner_client.get(reverse("catalog:kitchen", args=[gratin.pk])).content.decode()

    assert page.count("data-step") == len(gratin.steps)
    assert "data-prev" in page and "data-next" in page and "data-timers" in page
    assert "Extra Crisp" in page and "8 min sous pression" in page


def test_kitchen_page_loads_its_scripts_without_inline_code(owner_client, gratin):
    page = owner_client.get(reverse("catalog:kitchen", args=[gratin.pk])).content.decode()

    assert "js/durations.js" in page and "js/kitchen.js" in page
    assert not INLINE.search(page)


def test_steps_stay_readable_without_javascript(owner_client, gratin):
    page = owner_client.get(reverse("catalog:kitchen", args=[gratin.pk])).content.decode()

    assert "<ol" in page and gratin.steps[0] in page


def test_recipe_without_stored_steps_points_to_the_original_site(owner_client, gratin):
    Recipe.objects.filter(pk=gratin.pk).update(steps=[], url="https://example.test/r")

    page = owner_client.get(reverse("catalog:kitchen", args=[gratin.pk])).content.decode()

    assert "ne sont pas conservées" in page and "https://example.test/r" in page


def test_detail_page_links_to_kitchen_mode_only_when_there_are_steps(owner_client, gratin):
    assert (
        "Mode cuisine"
        in owner_client.get(reverse("catalog:detail", args=[gratin.pk])).content.decode()
    )
    Recipe.objects.filter(pk=gratin.pk).update(steps=[])

    assert (
        "Mode cuisine"
        not in owner_client.get(reverse("catalog:detail", args=[gratin.pk])).content.decode()
    )


def test_service_worker_precaches_the_kitchen_and_export_scripts(client, db):
    body = client.get("/sw.js").content.decode()

    assert "js/kitchen.js" in body and "js/durations.js" in body and "js/export.js" in body


def test_shopping_page_offers_export_buttons(owner_client, owner, db):
    from datetime import date

    from apps.households.models import Membership
    from apps.planner.models import MenuPlan

    plan = MenuPlan.objects.create(
        household=Membership.objects.get(user=owner).household,
        start_date=date.today(),
        end_date=date.today(),
        seed=1,
    )

    page = owner_client.get(reverse("shopping:detail", args=[plan.pk])).content.decode()

    assert (
        all(f'data-export="{a}"' in page for a in ("copy", "share", "print"))
        and "js/export.js" in page
    )
