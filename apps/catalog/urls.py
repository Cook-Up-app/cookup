from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.recipe_list, name="list"),
    path("importer", views.recipe_import, name="import"),
    path("nouvelle", views.recipe_create, name="create"),
    path("<uuid:pk>/", views.recipe_detail, name="detail"),
]
