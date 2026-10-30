from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("sante", views.health, name="health"),
    path("internal/cron/daily", views.cron_daily, name="cron-daily"),
]
