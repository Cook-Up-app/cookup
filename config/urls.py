from allauth.account.decorators import secure_admin_login
from allauth.account.views import LoginView, LogoutView, SignupView
from allauth.mfa.base.views import IndexView as SecurityView
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import password_reset_disabled
from apps.core.dev import dev_login
from apps.households.views import accept_invitation

urlpatterns = [
    path("", include("apps.core.urls")),
    # Pas de fournisseur d'e-mails : la réinitialisation passe par le propriétaire du foyer.
    # Placé avant allauth pour être résolu en premier (même chemin, donc même reverse).
    path("compte/password/reset/", password_reset_disabled, name="account_reset_password"),
    path("compte/", include("allauth.urls")),
    path("", include("apps.shopping.urls")),
    path("foyer/", include("apps.households.urls")),
    path("recettes/", include("apps.catalog.urls")),
    path("menus/", include("apps.planner.urls")),
    path("bienvenue/", include("apps.onboarding.urls")),
    path("invitation/<str:token>", accept_invitation, name="accept-invitation"),
    # Chemins français de la spec. Placés après allauth : `reverse` retient le dernier motif
    # portant un nom, et ces chemins n'entrent pas en conflit avec ceux d'allauth.
    path("connexion", LoginView.as_view(), name="account_login"),
    path("inscription", SignupView.as_view(), name="account_signup"),
    path("deconnexion", LogoutView.as_view(), name="account_logout"),
    path("compte/securite", SecurityView.as_view(), name="mfa_index"),
]

handler429 = "apps.core.views.too_many_requests"

if settings.DEV_LOGIN:
    urlpatterns.append(path("dev/connexion/<str:role>", dev_login, name="dev-login"))

if settings.ADMIN_PATH:
    admin.site.login = secure_admin_login(admin.site.login)
    urlpatterns.append(path(settings.ADMIN_PATH, admin.site.urls))
