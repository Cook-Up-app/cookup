from allauth.account.decorators import reauthentication_required
from allauth.account.internal.flows.reauthentication import reauthenticate_by_password
from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from . import services
from .exceptions import AccountAlreadyExists, InvitationInvalid, LastOwnerError
from .forms import (
    AcceptInvitationForm,
    DinerForm,
    EquipmentForm,
    HouseholdForm,
    InvitationForm,
    RestrictionForm,
)
from .models import Diner, DinerRestriction, HouseholdEquipment, Invitation, Membership
from .permissions import household_required, owner_required

AUTH_BACKEND = "allauth.account.auth_backends.AuthenticationBackend"


def _show_link_once(request: HttpRequest, label: str, path: str) -> None:
    messages.success(
        request, f"{label} (affiché une seule fois) : {request.build_absolute_uri(path)}"
    )


@require_http_methods(["GET", "POST"])
def household_home(request: HttpRequest) -> HttpResponse:
    membership = Membership.objects.filter(user=request.user).select_related("household").first()
    if membership is None:
        form = HouseholdForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            services.create_household(request.user, form.cleaned_data["name"])
            return redirect("households:home")
        return render(request, "households/create.html", {"form": form})
    household = membership.household
    context = {
        "household": household,
        "membership": membership,
        "members": Membership.objects.for_household(household).select_related("user"),
        "invitations": Invitation.objects.for_household(household).filter(used_at__isnull=True),
        "invitation_form": InvitationForm(),
    }
    return render(request, "households/home.html", context)


@require_POST
@owner_required
def invitation_create(request: HttpRequest) -> HttpResponse:
    form = InvitationForm(request.POST)
    if form.is_valid():
        _, raw_token = services.create_invitation(
            request.household, form.cleaned_data["email"], request.user
        )
        _show_link_once(
            request, "Lien d'invitation", reverse("accept-invitation", args=[raw_token])
        )
    else:
        messages.error(request, "Adresse e-mail invalide.")
    return redirect("households:home")


@require_POST
@owner_required
def invitation_revoke(request: HttpRequest, pk) -> HttpResponse:
    get_object_or_404(Invitation.objects.for_household(request.household), pk=pk).delete()
    return redirect("households:home")


@require_http_methods(["GET", "POST"])
@owner_required
@reauthentication_required(allow_get=True)
def member_remove(request: HttpRequest, pk) -> HttpResponse:
    if request.method == "POST":
        membership = get_object_or_404(Membership.objects.for_household(request.household), pk=pk)
        try:
            services.remove_member(membership)
        except LastOwnerError:
            messages.error(request, "Le dernier propriétaire ne peut pas être retiré.")
    else:
        messages.info(request, "Identité confirmée : relancez l'action.")
    return redirect("households:home")


@require_http_methods(["GET", "POST"])
@owner_required
@reauthentication_required(allow_get=True)
def member_reset_link(request: HttpRequest, pk) -> HttpResponse:
    if request.method == "POST":
        membership = get_object_or_404(
            Membership.objects.for_household(request.household).select_related("user"), pk=pk
        )
        _show_link_once(
            request,
            f"Lien de réinitialisation pour {membership.user}",
            services.build_password_reset_path(membership.user),
        )
    else:
        messages.info(request, "Identité confirmée : relancez l'action.")
    return redirect("households:home")


@require_http_methods(["GET", "POST"])
@household_required
def diner_list(request: HttpRequest) -> HttpResponse:
    form = DinerForm(request.POST or None)
    if request.method == "POST":
        if not request.membership.is_owner:
            return redirect("households:diners")
        if form.is_valid():
            diner = form.save(commit=False)
            diner.household = request.household
            diner.save()
            return redirect("households:diner", pk=diner.pk)
    diners = Diner.objects.for_household(request.household).prefetch_related("restrictions")
    return render(request, "households/diners.html", {"diners": diners, "form": form})


@require_http_methods(["GET", "POST"])
@household_required
def diner_detail(request: HttpRequest, pk) -> HttpResponse:
    diner = get_object_or_404(
        Diner.objects.for_household(request.household).prefetch_related("restrictions"), pk=pk
    )
    form = DinerForm(request.POST or None, instance=diner)
    if request.method == "POST" and request.membership.is_owner and form.is_valid():
        form.save()
        return redirect("households:diner", pk=diner.pk)
    context = {"diner": diner, "form": form, "restriction_form": RestrictionForm()}
    return render(request, "households/diner.html", context)


@require_POST
@owner_required
def diner_delete(request: HttpRequest, pk) -> HttpResponse:
    get_object_or_404(Diner.objects.for_household(request.household), pk=pk).delete()
    return redirect("households:diners")


@require_POST
@owner_required
def restriction_add(request: HttpRequest, pk) -> HttpResponse:
    diner = get_object_or_404(Diner.objects.for_household(request.household), pk=pk)
    form = RestrictionForm(request.POST)
    if form.is_valid():
        restriction = form.save(commit=False)
        restriction.diner = diner
        restriction.save()
    else:
        messages.error(request, "Indiquez un allergène ou un ingrédient.")
    return redirect("households:diner", pk=diner.pk)


@require_POST
@owner_required
def restriction_delete(request: HttpRequest, pk) -> HttpResponse:
    restriction = get_object_or_404(
        DinerRestriction.objects.for_household(request.household).select_related("diner"), pk=pk
    )
    diner_pk = restriction.diner_id
    restriction.delete()
    return redirect("households:diner", pk=diner_pk)


@require_http_methods(["GET", "POST"])
@household_required
def equipment(request: HttpRequest) -> HttpResponse:
    owned = HouseholdEquipment.objects.for_household(request.household)
    form = EquipmentForm(
        request.POST or None, initial={"equipment": owned.values_list("equipment", flat=True)}
    )
    if request.method == "POST" and request.membership.is_owner and form.is_valid():
        services.set_equipment(request.household, form.cleaned_data["equipment"])
        return redirect("households:equipment")
    return render(request, "households/equipment.html", {"form": form})


@require_http_methods(["GET", "POST"])
def accept_invitation(request: HttpRequest, token: str) -> HttpResponse:
    try:
        invitation = services.find_valid_invitation(token)
    except InvitationInvalid:
        return render(request, "households/invitation_invalid.html", status=404)
    form = AcceptInvitationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = services.accept_invitation(
                token, form.cleaned_data["display_name"], form.cleaned_data["password1"]
            )
        except ValidationError as error:
            form.add_error("password1", error)
        except (InvitationInvalid, AccountAlreadyExists):
            return render(request, "households/invitation_invalid.html", status=404)
        else:
            login(request, user, backend=AUTH_BACKEND)
            # L'activation de la MFA exige une authentification récente : celle-ci compte.
            reauthenticate_by_password(request)
            return redirect("mfa_index")
    return render(
        request, "households/accept_invitation.html", {"form": form, "invitation": invitation}
    )
