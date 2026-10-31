class HouseholdError(Exception):
    """Base des erreurs métier du foyer."""


class InvitationInvalid(HouseholdError):
    """Jeton inconnu, expiré ou déjà utilisé (les trois cas sont volontairement indiscernables)."""


class AccountAlreadyExists(HouseholdError):
    """Un compte existe déjà pour l'adresse invitée."""


class LastOwnerError(HouseholdError):
    """Le dernier propriétaire d'un foyer ne peut pas être retiré."""
