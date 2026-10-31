import json
import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.households.models import Membership
from apps.planner.models import MenuPlan, MenuSlot
from apps.shopping import services
from apps.shopping.models import ShoppingItem
from tests.conftest import make_user, seed_catalog

TODAY = timezone.localdate()


def millis(moment) -> int:
    return int(moment.timestamp() * 1000)


@pytest.fixture
def ready(owner_client, owner, db):
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    plan = MenuPlan.objects.create(household=household, start_date=TODAY, end_date=TODAY, seed=1)
    MenuSlot.objects.create(
        plan=plan, day=TODAY, meal_type="dinner", servings=4,
        recipe=Recipe.objects.get(title="Gratin de courgettes"),
    )  # fmt: skip
    shopping_list = services.sync_list(plan)
    return owner_client, plan, shopping_list


def post(client, plan, operations, **extra):
    return client.post(
        reverse("shopping:sync", args=[plan.pk]),
        data=json.dumps({"operations": operations}),
        content_type="application/json",
        **extra,
    )


def item_of(shopping_list, label="courgette") -> ShoppingItem:
    return shopping_list.items.get(label=label)


def op(item, checked=True, at=None, op_id="o1", kind="set"):
    return {
        "id": op_id,
        "type": kind,
        "item": str(item.pk),
        "checked": checked,
        "ts": millis(at or timezone.now()),
    }


def test_checking_is_applied_and_the_snapshot_comes_back(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)

    response = post(client, plan, [op(item)])

    body = response.json()
    item.refresh_from_db()
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert body["results"] == [{"id": "o1", "status": "applied"}] and item.checked
    assert next(i for i in body["items"] if i["id"] == str(item.pk))["checked"] is True


def test_replaying_the_same_operation_changes_nothing(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)
    operation = op(item, checked=True)

    for _ in range(3):
        assert post(client, plan, [operation]).json()["results"][0]["status"] == "applied"

    item.refresh_from_db()
    assert item.checked


def test_the_latest_gesture_wins_whatever_the_arrival_order(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)
    now = timezone.now()
    newer = op(item, checked=False, at=now, op_id="new")
    older = op(item, checked=True, at=now - timedelta(minutes=10), op_id="old")

    post(client, plan, [newer])
    result = post(client, plan, [older]).json()["results"][0]

    item.refresh_from_db()
    assert result["status"] == "stale" and not item.checked


def test_two_devices_on_different_lines_never_conflict(ready):
    client, plan, shopping_list = ready
    first, second = item_of(shopping_list, "courgette"), item_of(shopping_list, "crème liquide")

    results = post(client, plan, [op(first, op_id="a"), op(second, op_id="b")]).json()["results"]

    assert [r["status"] for r in results] == ["applied", "applied"]


def test_a_phone_clock_in_the_future_cannot_freeze_a_line(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)

    post(client, plan, [op(item, at=timezone.now() + timedelta(days=3650))])

    item.refresh_from_db()
    assert item.checked_at <= timezone.now() + timedelta(minutes=5, seconds=2)


def test_a_line_removed_by_a_recalculation_is_dropped_quietly(ready):
    client, plan, _ = ready
    ghost = {
        "id": "g",
        "type": "set",
        "item": str(uuid.uuid4()),
        "checked": True,
        "ts": millis(timezone.now()),
    }

    assert post(client, plan, [ghost]).json()["results"] == [{"id": "g", "status": "missing"}]


def test_an_item_added_offline_keeps_its_client_identifier_and_is_not_duplicated(ready):
    client, plan, shopping_list = ready
    new_id = str(uuid.uuid4())
    add = {
        "id": "a1",
        "type": "add",
        "item": new_id,
        "label": "Piles",
        "quantity": "2",
        "aisle": "misc",
        "ts": millis(timezone.now()),
    }

    first = post(client, plan, [add]).json()["results"][0]["status"]
    second = post(client, plan, [add]).json()["results"][0]["status"]

    created = ShoppingItem.objects.filter(pk=new_id)
    assert (first, second) == ("applied", "applied") and created.count() == 1
    assert created.get().manual and created.get().shopping_list == shopping_list


def test_an_added_item_cannot_take_over_an_item_of_another_list(ready):
    client, plan, _ = ready
    other_plan = MenuPlan.objects.create(
        household=plan.household, start_date=TODAY, end_date=TODAY, seed=2
    )
    foreign = services.add_manual_item(services.sync_list(other_plan), "Ailleurs")
    add = {
        "id": "x",
        "type": "add",
        "item": str(foreign.pk),
        "label": "Volé",
        "aisle": "misc",
        "ts": millis(timezone.now()),
    }

    assert post(client, plan, [add]).json()["results"][0]["status"] == "invalid"
    foreign.refresh_from_db()
    assert foreign.label == "Ailleurs"


def test_remove_operation_hides_a_calculated_line_and_deletes_a_manual_one(ready):
    client, plan, shopping_list = ready
    item, manual = item_of(shopping_list), services.add_manual_item(shopping_list, "Piles")

    post(client, plan, [op(item, kind="remove", op_id="r1"), op(manual, kind="remove", op_id="r2")])

    item.refresh_from_db()
    assert item.hidden and not ShoppingItem.objects.filter(pk=manual.pk).exists()


@pytest.mark.parametrize(
    "garbage",
    [
        "texte",
        42,
        None,
        {},
        {"type": "set"},
        {"type": "boom", "item": str(uuid.uuid4()), "ts": 1},
        {"type": "set", "item": "pas-un-uuid", "ts": 1},
        {"type": "set", "item": str(uuid.uuid4()), "ts": "x"},
        {"type": "add", "item": str(uuid.uuid4()), "label": "", "ts": 1},
        {"type": "add", "item": str(uuid.uuid4()), "label": "x", "aisle": "inconnu", "ts": 1},
        {"type": "add", "item": str(uuid.uuid4()), "label": "x", "quantity": "-5", "ts": 1},
        {"type": "set", "item": str(uuid.uuid4()), "ts": 10**30},
    ],
)
def test_malformed_operations_are_ignored_without_error(ready, garbage):
    client, plan, _ = ready

    response = post(client, plan, [garbage])

    assert response.status_code == 200 and response.json()["results"][0]["status"] == "invalid"


@pytest.mark.parametrize("body", ["pas du json", '{"operations": "x"}', "[1, 2]"])
def test_bad_request_bodies_are_rejected(ready, body):
    client, plan, _ = ready

    response = client.post(
        reverse("shopping:sync", args=[plan.pk]), data=body, content_type="application/json"
    )

    assert response.status_code == 400


def test_the_batch_is_capped(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)

    results = post(client, plan, [op(item, op_id=str(i)) for i in range(300)]).json()["results"]

    assert len(results) == 200


def test_csrf_protection_applies_to_synchronisation(ready, owner):
    _, plan, shopping_list = ready
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)

    response = post(strict, plan, [op(item_of(shopping_list))])

    assert response.status_code == 403


def test_csrf_cookie_value_is_accepted_as_header_token(ready, owner):
    """C'est ce que fera le JavaScript au retour du réseau : relire le cookie CSRF."""
    _, plan, shopping_list = ready
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)
    strict.get(reverse("shopping:detail", args=[plan.pk]))
    token = strict.cookies["csrftoken"].value

    response = post(strict, plan, [op(item_of(shopping_list))], HTTP_X_CSRFTOKEN=token)

    assert response.status_code == 200


def test_foreign_plan_cannot_be_synchronised(ready, other_owner):
    client, _, _ = ready
    foreign = MenuPlan.objects.create(
        household=Membership.objects.get(user=other_owner).household,
        start_date=TODAY,
        end_date=TODAY,
        seed=3,
    )

    assert post(client, foreign, []).status_code == 404


def test_foreign_items_cannot_be_altered_through_my_plan(ready, other_owner):
    client, plan, _ = ready
    foreign_plan = MenuPlan.objects.create(
        household=Membership.objects.get(user=other_owner).household,
        start_date=TODAY,
        end_date=TODAY,
        seed=3,
    )
    foreign_item = services.add_manual_item(services.sync_list(foreign_plan), "Secret")

    result = post(client, plan, [op(foreign_item)]).json()["results"][0]

    foreign_item.refresh_from_db()
    assert result["status"] == "missing" and not foreign_item.checked


def test_anonymous_and_get_requests_are_refused(ready):
    owner_client, plan, _ = ready
    anonymous = Client()

    assert anonymous.post(reverse("shopping:sync", args=[plan.pk])).status_code == 302
    assert owner_client.get(reverse("shopping:sync", args=[plan.pk])).status_code == 405


def test_simple_member_can_synchronise(client, ready):
    _, plan, shopping_list = ready
    member = make_user("member@example.com", mfa=False)
    Membership.objects.create(user=member, household=plan.household)
    client.force_login(member)

    assert post(client, plan, [op(item_of(shopping_list))]).status_code == 200


def test_page_exposes_what_the_script_needs(ready):
    client, plan, _ = ready

    page = client.get(reverse("shopping:detail", args=[plan.pk])).content.decode()

    assert "data-shopping" in page and f"/courses/{plan.pk}/synchroniser" in page
    assert 'data-action="toggle"' in page and 'data-csrf-cookie="csrftoken"' in page


def test_the_form_fallback_also_records_the_time_of_the_gesture(ready):
    client, plan, shopping_list = ready
    item = item_of(shopping_list)

    client.post(reverse("shopping:toggle", args=[plan.pk, item.pk]))

    item.refresh_from_db()
    assert item.checked and item.checked_at is not None
