"""Interface : navigation, structure des pages, accessibilité de base, CSP et pages d'erreur."""

import re
from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.catalog.models import Recipe
from apps.households.models import Diner, HouseholdEquipment, Membership
from apps.planner import services as planner_services
from apps.shopping import services as shopping_services
from tests.conftest import seed_catalog

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)
INLINE_STYLE = re.compile(r"""<[a-z][^>]*\sstyle=["']""", re.I)
INLINE_HANDLER = re.compile(r"""<[a-z][^>]*\son[a-z]+=["']""", re.I)


@pytest.fixture
def site(owner_client, owner, db):
    """Un foyer avec menu, courses et recette : de quoi visiter toutes les pages."""
    seed_catalog()
    household = Membership.objects.get(user=owner).household
    for code in ("hob", "oven"):
        HouseholdEquipment.objects.create(household=household, equipment_id=code)
    diner = Diner.objects.create(household=household, first_name="Léa")
    today = date.today()
    plan = planner_services.create_plan(
        household,
        planner_services.PlanRequest(
            start_date=today, end_date=today + timedelta(days=1), meals=("lunch", "dinner"),
            diner_ids=(str(diner.pk),),
        ),
        today,
        seed=5,
    )  # fmt: skip
    shopping_services.sync_list(plan)
    recipe = Recipe.objects.get(title="Gratin de courgettes")
    slot = plan.slots.first()
    return {
        "client": owner_client,
        "household": household,
        "plan": plan,
        "recipe": recipe,
        "diner": diner,
        "slot": slot,
    }


def pages(site) -> dict[str, str]:
    plan, recipe, diner, slot = site["plan"], site["recipe"], site["diner"], site["slot"]
    return {
        "accueil": reverse("core:home"),
        "plus": reverse("core:more"),
        "menus": reverse("planner:list"),
        "menu-nouveau": reverse("planner:new"),
        "menu": reverse("planner:detail", args=[plan.pk]),
        "courses": reverse("shopping:detail", args=[plan.pk]),
        "placard": reverse("shopping:pantry"),
        "rayons": reverse("shopping:aisles"),
        "recettes": reverse("catalog:list"),
        "recette": reverse("catalog:detail", args=[recipe.pk]),
        "cuisine": reverse("catalog:kitchen", args=[recipe.pk]),
        "import": reverse("catalog:import"),
        "creation": reverse("catalog:create"),
        "foyer": reverse("households:home"),
        "convives": reverse("households:diners"),
        "convive": reverse("households:diner", args=[diner.pk]),
        "gouts": reverse("households:diner-tastes", args=[diner.pk]),
        "equipements": reverse("households:equipment"),
        "preferences": reverse("households:preferences"),
        "securite": reverse("mfa_index"),
        "hors-ligne": reverse("core:offline"),
        "remplacer-vue": reverse("planner:detail", args=[plan.pk]) + "#" + str(slot.pk),
    }


def test_every_page_renders_with_a_clean_structure(site):
    client = site["client"]

    for name, url in pages(site).items():
        response = client.get(url)
        page = response.content.decode()

        assert response.status_code == 200, name
        assert (
            '<html lang="fr">' in page
            and 'name="viewport"' in page
            and "viewport-fit=cover" in page
        ), name
        assert page.count("<h1") == 1, name
        assert '<main id="main"' in page and 'class="skip-link"' in page, name
        assert not INLINE_SCRIPT.search(page), f"script inline : {name}"
        assert not INLINE_STYLE.search(page), f"style inline (bloqué par la CSP) : {name}"
        assert not INLINE_HANDLER.search(page), f"gestionnaire inline : {name}"


def test_app_pages_have_both_navigations_with_the_current_page_marked(site):
    page = site["client"].get(reverse("planner:list")).content.decode()

    assert 'class="bottom-nav"' in page and 'class="sidebar"' in page
    assert page.count('aria-current="page"') == 2  # barre du bas + menu latéral
    assert re.search(r'<a class="nav-item" href="/menus/" aria-current="page">', page)


@pytest.mark.parametrize(
    ("name", "current"),
    [
        ("core:home", "Accueil"),
        ("catalog:list", "Recettes"),
        ("shopping:pantry", "Plus"),
        ("households:diners", "Plus"),
        ("mfa_index", "Plus"),
    ],
)
def test_the_right_bottom_tab_is_highlighted(site, name, current):
    page = site["client"].get(reverse(name)).content.decode()

    active = re.findall(
        r'<a class="nav-item"[^>]*aria-current="page"><svg[^>]*>.*?</svg><span>(.*?)</span>', page
    )

    assert active == [current]


def test_courses_tab_follows_the_shopping_pages(site):
    page = site["client"].get(reverse("shopping:detail", args=[site["plan"].pk])).content.decode()

    assert re.search(r'href="/courses/" aria-current="page"', page)


def test_more_page_lists_everything_that_is_not_in_the_bottom_bar(site):
    page = site["client"].get(reverse("core:more")).content.decode()

    for label in (
        "Foyer",
        "Convives",
        "Équipements",
        "Préférences",
        "Placard",
        "Sécurité",
        "Se déconnecter",
    ):
        assert label in page


def test_logout_is_a_post_form_everywhere(site):
    for url in (reverse("core:more"), reverse("core:home")):
        page = site["client"].get(url).content.decode()
        assert re.search(r'<form method="post" action="/deconnexion"', page)


def test_courses_tab_redirects_to_the_latest_list_or_explains(site, owner):
    assert site["client"].get(reverse("shopping:index"))["Location"] == reverse(
        "shopping:detail", args=[site["plan"].pk]
    )
    site["plan"].delete()

    page = site["client"].get(reverse("shopping:index")).content.decode()

    assert "Pas encore de liste de courses" in page and reverse("planner:new") in page


def test_dashboard_shows_today_and_the_shopping_shortcut(site):
    page = site["client"].get(reverse("core:home")).content.decode()

    assert "Aujourd'hui" in page and "Ouvrir la liste" in page and "Nouveau menu" in page
    assert escape_title(site["plan"].slots.first().recipe.title) in page


def escape_title(title: str) -> str:
    from django.utils.html import escape

    return escape(title)


def test_dashboard_without_a_menu_invites_to_create_one(owner_client, owner, db):
    from apps.households.models import Diner

    Diner.objects.create(household=Membership.objects.get(user=owner).household, first_name="Léa")

    page = owner_client.get(reverse("core:home")).content.decode()

    assert "Votre premier menu vous attend" in page


def test_forms_render_choices_as_chips_and_wrap_fields(site):
    page = site["client"].get(reverse("planner:new")).content.decode()

    assert 'class="chips"' in page and page.count('class="chip"') >= 8
    assert (
        'class="field' in page and 'type="range"' in page and 'id="id_cookeo_share_value"' in page
    )
    assert 'type="date"' in page and "Générer le menu" in page


def test_form_errors_are_shown_next_to_the_field(site):
    page = (
        site["client"]
        .post(reverse("catalog:create"), {"title": "", "servings": 4})
        .content.decode()
    )

    assert "has-error" in page and 'class="errorlist"' in page


def test_star_rating_is_five_radio_buttons_in_a_group(site):
    page = site["client"].get(reverse("catalog:detail", args=[site["recipe"].pk])).content.decode()

    assert 'role="radiogroup"' in page and len(re.findall(r'name="rating"', page)) == 5


def test_recipe_photos_are_lazy_and_do_not_leak_the_referrer(site):
    Recipe.objects.filter(pk=site["recipe"].pk).update(
        image_url="https://assets.afcdn.com/recipe/x.jpg"
    )

    page = site["client"].get(reverse("catalog:list"), {"q": "gratin courgettes"}).content.decode()

    assert 'src="https://assets.afcdn.com/recipe/x.jpg"' in page
    assert 'loading="lazy"' in page and 'referrerpolicy="no-referrer"' in page


def test_csp_allows_only_the_declared_image_servers(site):
    policy = site["client"].get(reverse("core:home")).headers["Content-Security-Policy"]

    assert "img-src 'self' data: https://assets.afcdn.com" in policy
    assert "unsafe-inline" not in policy and "https:" not in policy.replace("https://assets", "")


def test_image_servers_can_be_configured(monkeypatch):
    import importlib

    monkeypatch.setenv("SOURCES_IMAGE_DOMAINS", "img.one.test,img.two.test")
    from config.settings import base

    reloaded = importlib.reload(base)
    try:
        assert "https://img.two.test" in reloaded.SECURE_CSP["img-src"]
    finally:
        monkeypatch.delenv("SOURCES_IMAGE_DOMAINS")
        importlib.reload(base)


def test_unknown_pages_get_a_friendly_404(client, db):
    response = client.get("/cette-page-n-existe-pas")

    assert response.status_code == 404 and "Page introuvable" in response.content.decode()


def test_csrf_failure_explains_what_happened(owner, db):
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)

    response = strict.post(reverse("planner:generate"), {})

    assert response.status_code == 403 and "Votre page a expiré" in response.content.decode()


def test_server_error_page_is_standalone(client, db):
    from django.template.loader import render_to_string

    page = render_to_string("500.html")

    assert (
        "Un problème est survenu" in page and "<script" not in page and "csrf" not in page.lower()
    )


def test_login_page_is_the_new_design(client, db):
    page = client.get(reverse("account_login")).content.decode()

    assert 'class="auth-card' in page and "Se connecter" in page and "Mot de passe oublié" in page
    assert "If you have not created an account" not in page


def test_stylesheets_exist_for_every_link(client, db):
    page = client.get(reverse("account_login")).content.decode()
    from django.contrib.staticfiles import finders

    for href in re.findall(r'href="/static/([^"]+\.css)"', page):
        assert finders.find(href), href
    for src in re.findall(r'src="/static/([^"]+\.js)"', page):
        assert finders.find(src), src


def test_design_tokens_pass_wcag_contrast():
    """Les couleurs de texte et de boutons respectent le ratio AA, en clair et en sombre."""
    from pathlib import Path

    css = (
        Path(__file__).resolve().parent.parent.parent / "static" / "css" / "tokens.css"
    ).read_text()
    light, dark = css.split("@media (prefers-color-scheme: dark)")

    def colours(block):
        return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))

    def luminance(hex_colour):
        channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def ratio(a, b):
        high, low = sorted((luminance(a), luminance(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for theme in (colours(light), colours(dark)):
        text_pairs = [
            ("text", "bg"), ("text", "surface"), ("text-muted", "bg"), ("text-muted", "surface"),
            ("accent", "bg"), ("on-accent", "accent"), ("accent-ink", "accent-soft"),
            ("danger", "danger-soft"), ("warning", "warning-soft"),
        ]  # fmt: skip
        for foreground, background in text_pairs:
            assert ratio(theme[foreground], theme[background]) >= 4.5, (foreground, background)
        assert ratio(theme["border-strong"], theme["surface"]) >= 3.0
        assert ratio(theme["focus"], theme["bg"]) >= 3.0
