import pytest
from django.urls import reverse

from apps.households.models import Diner, DinerRestriction, Membership

MAX_QUERIES_PER_PAGE = 15  # budget de la section 14


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["households:home", "households:diners", "households:equipment"])
def test_pages_stay_within_query_budget(owner_client, owner, django_assert_max_num_queries, name):
    household = Membership.objects.get(user=owner).household
    for index in range(10):  # un N+1 ferait exploser le compteur
        diner = Diner.objects.create(household=household, first_name=f"Convive {index}")
        DinerRestriction.objects.create(diner=diner, allergen="milk")

    with django_assert_max_num_queries(MAX_QUERIES_PER_PAGE):
        assert owner_client.get(reverse(name)).status_code == 200
