"""Protection SSRF : schémas, domaines autorisés et adresses publiques seulement."""

import ipaddress
import socket
from urllib.parse import urlsplit

from .exceptions import FetchRefused

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def ensure_public_address(address: str) -> None:
    """Refuse les adresses privées, locales, de boucle et de métadonnées cloud."""
    if not _public(address):
        raise FetchRefused("Adresse non publique refusée.")


def domain_allowed(host: str, allowed_domains: frozenset[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def validate_url(url: str, allowed_domains: frozenset[str]) -> str:
    """Valide l'URL puis la résolution DNS ; retourne l'hôte normalisé."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname:
        raise FetchRefused("Schéma ou hôte invalide.")
    if parts.username or parts.password:
        raise FetchRefused("Identifiants dans l'URL refusés.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise FetchRefused("Port refusé.")
    host = parts.hostname.lower().rstrip(".")
    if not domain_allowed(host, allowed_domains):
        raise FetchRefused("Domaine hors de la liste autorisée.")
    _check_resolution(host, port)
    return host


def _check_resolution(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise FetchRefused("Résolution DNS impossible.") from error
    for info in infos:
        ensure_public_address(info[4][0])
