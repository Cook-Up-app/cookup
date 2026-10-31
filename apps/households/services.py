"""Logique métier des foyers : création, invitations, retrait de membres."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .exceptions import AccountAlreadyExists, InvitationInvalid, LastOwnerError
from .models import Household, HouseholdEquipment, Invitation, Membership

TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


@transaction.atomic
def create_household(user, name: str) -> Household:
    household = Household.objects.create(name=name)
    Membership.objects.create(user=user, household=household, role=Membership.Role.OWNER)
    return household


def create_invitation(household: Household, email: str, invited_by) -> tuple[Invitation, str]:
    """Retourne l'invitation et le jeton en clair, qui n'est jamais stocké."""
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    invitation = Invitation.objects.create(
        household=household,
        email=email.strip().lower(),
        token_hash=_hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=settings.INVITATION_TTL_DAYS),
        invited_by=invited_by,
    )
    return invitation, raw_token


def find_valid_invitation(raw_token: str) -> Invitation:
    """Jeton inconnu, expiré ou utilisé : même erreur, pour ne rien révéler."""
    invitation = (
        Invitation.objects.filter(token_hash=_hash_token(raw_token))
        .select_related("household")
        .first()
    )
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.expires_at <= timezone.now()
        or not hmac.compare_digest(invitation.token_hash, _hash_token(raw_token))
    ):
        raise InvitationInvalid
    return invitation


@transaction.atomic
def accept_invitation(raw_token: str, display_name: str, password: str):
    """Crée le compte invité, l'ajoute au foyer et consomme le jeton."""
    invitation = find_valid_invitation(raw_token)
    user_model = get_user_model()
    if user_model.objects.filter(email__iexact=invitation.email).exists():
        raise AccountAlreadyExists
    user = user_model(email=invitation.email, display_name=display_name)
    validate_password(password, user)
    user.set_password(password)
    user.save()
    Membership.objects.create(user=user, household=invitation.household)
    invitation.used_at = timezone.now()
    invitation.save(update_fields=["used_at"])
    return user


@transaction.atomic
def remove_member(membership: Membership) -> None:
    if membership.is_owner:
        owners = Membership.objects.for_household(membership.household).filter(
            role=Membership.Role.OWNER
        )
        if owners.count() <= 1:
            raise LastOwnerError
    membership.delete()


def build_password_reset_path(user) -> str:
    """Chemin du lien de réinitialisation d'allauth, valable `PASSWORD_RESET_TIMEOUT`."""
    return reverse(
        "account_reset_password_from_key",
        kwargs={
            "uidb36": user_pk_to_url_str(user),
            "key": default_token_generator.make_token(user),
        },
    )


@transaction.atomic
def set_equipment(household: Household, equipment) -> None:
    """Remplace l'équipement du foyer par la sélection donnée."""
    HouseholdEquipment.objects.for_household(household).exclude(equipment__in=equipment).delete()
    for item in equipment:
        HouseholdEquipment.objects.get_or_create(household=household, equipment=item)
