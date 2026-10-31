class SourceError(Exception):
    """Base des erreurs liées aux sources de recettes."""


class FetchRefused(SourceError):
    """Requête refusée avant envoi : schéma, domaine, adresse privée ou robots.txt."""


class SourceUnavailable(SourceError):
    """Source en panne, bloquante ou en pause : on s'arrête sans insister."""


class FetchFailed(SourceError):
    """Réponse inexploitable (statut d'erreur, trop volumineuse, type inattendu)."""


class ParseFailed(SourceError):
    """La page ne contient pas de recette exploitable."""
