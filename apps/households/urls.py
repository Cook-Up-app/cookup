from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("", views.household_home, name="home"),
    path("invitations/", views.invitation_create, name="invitation-create"),
    path("invitations/<uuid:pk>/revoquer", views.invitation_revoke, name="invitation-revoke"),
    path("membres/<uuid:pk>/retirer", views.member_remove, name="member-remove"),
    path(
        "membres/<uuid:pk>/lien-reinitialisation", views.member_reset_link, name="member-reset-link"
    ),
    path("convives/", views.diner_list, name="diners"),
    path("convives/<uuid:pk>/", views.diner_detail, name="diner"),
    path("convives/<uuid:pk>/supprimer", views.diner_delete, name="diner-delete"),
    path("convives/<uuid:pk>/restrictions/", views.restriction_add, name="restriction-add"),
    path("restrictions/<uuid:pk>/supprimer", views.restriction_delete, name="restriction-delete"),
    path("equipements/", views.equipment, name="equipment"),
]
