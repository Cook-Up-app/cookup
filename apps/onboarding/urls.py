from django.urls import path

from . import views

app_name = "onboarding"

urlpatterns = [
    path("", views.start, name="start"),
    path("passer", views.dismiss, name="dismiss"),
    path("<slug:slug>/", views.wizard, name="step"),
    path("<slug:slug>/<uuid:key>/", views.wizard, name="step"),
]
