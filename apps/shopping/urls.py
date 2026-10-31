from django.urls import path

from . import views

app_name = "shopping"

urlpatterns = [
    path("courses/rayons", views.aisle_order, name="aisles"),
    path("courses/<uuid:plan_pk>/", views.shopping_detail, name="detail"),
    path("courses/<uuid:plan_pk>/regenerer", views.shopping_regenerate, name="regenerate"),
    path("courses/<uuid:plan_pk>/ajouter", views.item_add, name="add"),
    path("courses/<uuid:plan_pk>/lignes/<uuid:item_pk>/cocher", views.item_toggle, name="toggle"),
    path(
        "courses/<uuid:plan_pk>/lignes/<uuid:item_pk>/supprimer", views.item_remove, name="remove"
    ),
    path("foyer/placard/", views.pantry, name="pantry"),
    path("foyer/placard/<int:pk>/supprimer", views.pantry_remove, name="pantry-remove"),
]
