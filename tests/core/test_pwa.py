import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

ROOT = Path(__file__).resolve().parent.parent.parent
EXECUTABLE_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)


def test_manifest_is_valid_and_installable(client, db):
    response = client.get(reverse("core:manifest"))

    data = json.loads(response.content)
    assert response.status_code == 200 and response["Content-Type"].startswith(
        "application/manifest+json"
    )
    assert data["display"] == "standalone" and data["scope"] == "/" and data["lang"] == "fr"
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in data["icons"]:
        assert finders.find(icon["src"].removeprefix("/static/")), icon["src"]


def test_service_worker_is_served_at_the_root_with_the_right_headers(client, db, settings):
    settings.APP_VERSION = "abc123"

    response = client.get("/sw.js")

    body = response.content.decode()
    assert response.status_code == 200 and response["Content-Type"].startswith("text/javascript")
    assert response["Cache-Control"] == "no-cache" and response["Service-Worker-Allowed"] == "/"
    assert 'const VERSION = "abc123"' in body


def test_service_worker_precaches_existing_assets_only(client, db):
    body = client.get("/sw.js").content.decode()

    urls = json.loads(re.search(r"const SHELL_URLS = (\[.*?\]);", body).group(1))
    assert "/hors-ligne" in urls and "/manifest.webmanifest" in urls
    for url in (u for u in urls if u.startswith("/static/")):
        assert finders.find(url.removeprefix("/static/")), url


def test_service_worker_never_caches_sensitive_or_mutating_requests(client, db):
    body = client.get("/sw.js").content.decode()

    assert 'request.method !== "GET"' in body
    assert "connexion|deconnexion|compte|internal|invitation|admin" in body
    assert "caches.delete(PAGES)" in body  # effacement à la déconnexion


def test_offline_page_and_assets_are_public(client, db):
    for name in ("core:offline", "core:manifest", "core:service-worker"):
        assert client.get(reverse(name)).status_code == 200


def test_pages_link_the_manifest_and_scripts_without_inline_code(owner_client):
    page = owner_client.get(reverse("catalog:list")).content.decode()

    assert 'rel="manifest"' in page and 'name="theme-color"' in page
    assert "js/offline.js" in page and "js/outbox.js" in page
    assert not EXECUTABLE_INLINE_SCRIPT.search(page)


def test_content_security_policy_stays_strict_with_the_service_worker(client, db):
    policy = client.get("/sw.js").headers["Content-Security-Policy"]

    assert "unsafe-inline" not in policy and "script-src 'self'" in policy


@pytest.mark.skipif(shutil.which("node") is None, reason="node n'est pas installé")
def test_javascript_unit_tests_pass():
    tests = sorted((ROOT / "tests" / "js").glob("*.test.js"))

    result = subprocess.run(  # noqa: S603 - commande fixe, fichiers du dépôt
        [shutil.which("node"), "--test", *map(str, tests)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
