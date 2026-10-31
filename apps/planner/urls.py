from django.urls import path

from . import views

app_name = "planner"

urlpatterns = [
    path("", views.menu_list, name="list"),
    path("nouveau", views.menu_new, name="new"),
    path("generer", views.menu_generate, name="generate"),
    path("<uuid:pk>/", views.menu_detail, name="detail"),
    path("<uuid:pk>/regenerer", views.menu_regenerate, name="regenerate"),
    path("<uuid:pk>/creneaux/<uuid:slot_pk>/verrouiller", views.slot_lock, name="lock"),
    path("<uuid:pk>/creneaux/<uuid:slot_pk>/remplacer", views.slot_replace, name="replace"),
    path(
        "<uuid:pk>/creneaux/<uuid:slot_pk>/hors-maison", views.slot_out_of_home, name="out-of-home"
    ),
]
