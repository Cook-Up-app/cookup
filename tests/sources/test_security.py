import socket

import pytest

from apps.sources.exceptions import FetchRefused
from apps.sources.security import validate_url

ALLOWED = frozenset({"marmiton.org"})


@pytest.mark.parametrize(
    "url",
    [
        "ftp://www.marmiton.org/x",
        "file:///etc/passwd",
        "gopher://www.marmiton.org/",
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://2130706433/",
        "http://user:pass@www.marmiton.org/x",
        "https://www.marmiton.org:8443/x",
        "https://evil.example/x",
        "https://marmiton.org.evil.example/x",
        "https://notmarmiton.org/x",
        "",
        "pas une url",
    ],
)
def test_dangerous_or_foreign_urls_are_refused(url):
    with pytest.raises(FetchRefused):
        validate_url(url, ALLOWED)


def test_allowed_domain_and_subdomains_pass():
    assert validate_url("https://www.marmiton.org/recettes/x.aspx", ALLOWED) == "www.marmiton.org"
    assert validate_url("https://marmiton.org/", ALLOWED) == "marmiton.org"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.0.5",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "fd00::1",
        "100.64.0.1",
    ],
)
def test_allowed_domain_resolving_to_private_address_is_refused(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", (address, port))]
    )

    with pytest.raises(FetchRefused):
        validate_url("https://www.marmiton.org/x", ALLOWED)


def test_any_private_address_among_several_is_enough_to_refuse(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kw: [
            (2, 1, 6, "", ("93.184.216.34", port)),
            (2, 1, 6, "", ("10.0.0.1", port)),
        ],
    )

    with pytest.raises(FetchRefused):
        validate_url("https://www.marmiton.org/x", ALLOWED)


def test_unresolvable_host_is_refused(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", fail)

    with pytest.raises(FetchRefused):
        validate_url("https://www.marmiton.org/x", ALLOWED)
