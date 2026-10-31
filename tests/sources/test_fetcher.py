import pytest

from apps.sources.exceptions import FetchFailed, FetchRefused, SourceUnavailable
from apps.sources.http import PoliteFetcher, RawResponse
from apps.sources.models import SourceState
from apps.sources.ratelimit import DatabaseRateLimiter
from tests.sources.conftest import USER_AGENT, FakeTransport, html

RECIPE = "https://www.marmiton.org/recettes/recette_x_1.aspx"


@pytest.mark.django_db
def test_fetches_an_allowed_page(make_fetcher):
    fetcher, transport = make_fetcher({RECIPE: html("<p>ok</p>")})

    result = fetcher.get(RECIPE)

    assert result.text == "<p>ok</p>"
    assert transport.requested == ["https://www.marmiton.org/robots.txt", RECIPE]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/mon-espace/profil",
        "/recettes/recette-impression_x.aspx",
        "/recettes/recherche.aspx?type=dessert&aqt=gateau",
        "/recettes/recherche.aspx?aqt=poulet&page=2",
        "/recettes/recherche.aspx?aqt=poulet&start=10",
    ],
)
def test_robots_txt_is_obeyed_and_nothing_is_sent(make_fetcher, path):
    fetcher, transport = make_fetcher()

    with pytest.raises(FetchRefused):
        fetcher.get(f"https://www.marmiton.org{path}")

    assert transport.requested == ["https://www.marmiton.org/robots.txt"]


@pytest.mark.django_db
def test_plain_search_is_allowed_by_robots(make_fetcher):
    url = "https://www.marmiton.org/recettes/recherche.aspx?aqt=poulet"
    fetcher, _ = make_fetcher({url: html()})

    assert fetcher.get(url).status == 200


@pytest.mark.django_db
def test_robots_txt_is_fetched_once_per_host(make_fetcher):
    fetcher, transport = make_fetcher({RECIPE: html(), RECIPE + "2": html()})

    fetcher.get(RECIPE)
    fetcher.get(RECIPE + "2")

    assert transport.requested.count("https://www.marmiton.org/robots.txt") == 1


@pytest.mark.django_db
def test_missing_robots_txt_allows_everything(make_fetcher):
    fetcher, _ = make_fetcher({RECIPE: html()}, robots=None)

    assert fetcher.get(RECIPE).status == 200


@pytest.mark.django_db
def test_unreachable_robots_txt_forbids_everything(make_fetcher):
    broken = {"https://www.marmiton.org/robots.txt": RawResponse(500, {}, b"")}
    fetcher, transport = make_fetcher(broken, robots=None)

    with pytest.raises(FetchRefused):
        fetcher.get(RECIPE)

    assert RECIPE not in transport.requested


@pytest.mark.django_db
def test_requests_are_spaced_by_at_least_one_second(make_fetcher, clock):
    fetcher, _ = make_fetcher({RECIPE: html(), RECIPE + "2": html(), RECIPE + "3": html()})

    for suffix in ("", "2", "3"):
        fetcher.get(RECIPE + suffix)

    assert clock.slept and all(delay == pytest.approx(1.0) for delay in clock.slept)
    assert len(clock.slept) == 3  # robots.txt compte aussi comme une requête


@pytest.mark.django_db
def test_crawl_delay_is_honoured(make_fetcher, clock):
    fetcher, _ = make_fetcher({RECIPE: html()}, robots="User-agent: *\nCrawl-delay: 5\n")

    fetcher.get(RECIPE)

    assert 5.0 in [round(delay) * 1.0 for delay in clock.slept]


@pytest.mark.django_db
@pytest.mark.parametrize("status", [429, 503])
def test_blocking_response_pauses_the_source(make_fetcher, status):
    fetcher, transport = make_fetcher({RECIPE: RawResponse(status, {"retry-after": "120"}, b"")})

    with pytest.raises(SourceUnavailable):
        fetcher.get(RECIPE)
    with pytest.raises(SourceUnavailable):
        fetcher.get(RECIPE)

    assert transport.requested.count(RECIPE) == 1
    assert SourceState.objects.get(source="marmiton").cooldown_until is not None


@pytest.mark.django_db
def test_redirect_to_a_foreign_or_private_host_is_refused(make_fetcher):
    fetcher, transport = make_fetcher(
        {RECIPE: RawResponse(302, {"location": "http://169.254.169.254/latest/meta-data/"}, b"")}
    )

    with pytest.raises(FetchRefused):
        fetcher.get(RECIPE)

    assert all("169.254" not in url for url in transport.requested)


@pytest.mark.django_db
def test_redirect_loops_are_cut(make_fetcher):
    fetcher, _ = make_fetcher({RECIPE: RawResponse(302, {"location": RECIPE}, b"")})

    with pytest.raises(FetchFailed):
        fetcher.get(RECIPE)


@pytest.mark.django_db
def test_unexpected_content_type_and_errors_are_rejected(make_fetcher):
    fetcher, _ = make_fetcher(
        {
            RECIPE: RawResponse(200, {"content-type": "application/pdf"}, b"%PDF"),
            RECIPE + "404": RawResponse(404, {}, b""),
        }
    )

    with pytest.raises(FetchRefused):
        fetcher.get(RECIPE)
    with pytest.raises(FetchFailed):
        fetcher.get(RECIPE + "404")


@pytest.mark.django_db
def test_user_agent_must_carry_a_contact(clock):
    limiter = DatabaseRateLimiter("marmiton", sleep=clock.sleep, now=clock)

    with pytest.raises(SourceUnavailable):
        PoliteFetcher(
            user_agent="CookupBot/0.1",
            allowed_domains=frozenset({"marmiton.org"}),
            limiter=limiter,
            transport=FakeTransport(),
        )
    assert "contact" in USER_AGENT
