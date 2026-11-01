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

from . import restrictions
from .exceptions import AccountAlreadyExists, InvitationInvalid, LastOwnerError
from .models import (
    DinerRestriction,
    Household,
    HouseholdEquipment,
    Invitation,
    Membership,
    TastePreference,
)

TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


DEFAULT_HOUSEHOLD_NAME = "Mon foyer"


def ensure_household(user) -> Membership:
    """Adhésion du foyer de l'utilisateur ; crée un foyer personnel au premier passage."""
    membership = Membership.objects.filter(user=user).select_related("household").first()
    if membership is None:
        create_household(user, DEFAULT_HOUSEHOLD_NAME)
        membership = Membership.objects.select_related("household").get(user=user)
    return membership


@transaction.atomic
def create_household(user, name: str) -> Household:
    household = Household.objects.create(name=name)
    Membership.objects.create(user=user, household=household, role=Membership.Role.OWNER)
    return household


def create_invitation(household: Household, email: str, invited_by) -> tuple[Invitation, str]:
    """Retourne l'invitation et le jeton en clair, qui n'est jamais stocké."""
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    ttl_days = settings.INVITATION_TTL_DAYS
    invitation = Invitation.objects.create(
        household=household,
        email=email.strip().lower(),
        token_hash=_hash_token(raw_token),
        expires_at=timezone.now() + timedelta(days=ttl_days) if ttl_days else None,
        invited_by=invited_by,
    )
    return invitation, raw_token


def _is_expired(invitation: Invitation) -> bool:
    return invitation.expires_at is not None and invitation.expires_at <= timezone.now()


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
        or _is_expired(invitation)
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


LIKE_SCORE, DISLIKE_SCORE = 2, -2


@transaction.atomic
def set_tastes(diner, likes, dislikes, offered_ids) -> None:
    """Remplace les goûts du convive sur les ingrédients proposés ; les autres sont conservés."""
    TastePreference.objects.filter(diner=diner, ingredient_id__in=offered_ids).delete()
    TastePreference.objects.bulk_create(
        [TastePreference(diner=diner, ingredient=i, score=LIKE_SCORE) for i in likes]
        + [TastePreference(diner=diner, ingredient=i, score=DISLIKE_SCORE) for i in dislikes]
    )


STRICT = DinerRestriction.Severity.STRICT_ALLERGY


def _target_fields(target: restrictions.Target) -> dict[str, str]:
    field = {
        restrictions.Kind.ALLERGEN: "allergen",
        restrictions.Kind.GROUP: "food_group",
    }.get(target.kind, "ingredient_name")
    return {field: target.value}


def targets_from_input(allergens, groups, other: str) -> list[restrictions.Target]:
    """Cibles cochées puis saisies à la main ; une cible n'apparaît qu'une fois."""
    from apps.catalog.services import exact_name_resolver  # import paresseux : charge le catalogue

    found = [restrictions.Target(restrictions.Kind.ALLERGEN, code) for code in allergens]
    found += [restrictions.Target(restrictions.Kind.GROUP, code) for code in groups]
    terms = restrictions.split_terms(other)
    if terms:
        resolver = exact_name_resolver()
        found += [restrictions.recognise(term, resolver) for term in terms]
    unique: dict[tuple, restrictions.Target] = {}
    for target in found:
        unique.setdefault((target.kind, target.value.lower()), target)
    return list(unique.values())


@transaction.atomic
def add_restrictions(diner, severity: str, targets) -> None:
    """Enregistre chaque cible ; une restriction déjà présente prend la nouvelle gravité."""
    for target in targets:
        fields = _target_fields(target)
        key = {f"{name}__iexact": value for name, value in fields.items()}
        restriction = DinerRestriction.objects.filter(diner=diner, **key).first()
        if restriction is None:
            DinerRestriction.objects.create(diner=diner, severity=severity, **fields)
        elif restriction.severity != severity:
            restriction.severity = severity
            restriction.save(update_fields=["severity"])


@transaction.atomic
def sync_strict_selection(diner, allergens, groups) -> None:
    """Aligne les allergies strictes « allergène » et « famille » sur la sélection donnée."""
    for field, wanted in (("allergen", set(allergens)), ("food_group", set(groups))):
        current = DinerRestriction.objects.filter(diner=diner, severity=STRICT).exclude(
            **{field: ""}
        )
        current.exclude(**{f"{field}__in": wanted}).delete()
        have = set(current.values_list(field, flat=True))
        DinerRestriction.objects.bulk_create(
            DinerRestriction(diner=diner, severity=STRICT, **{field: code})
            for code in wanted - have
        )
