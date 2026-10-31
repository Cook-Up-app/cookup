from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("plus/", views.more, name="more"),
    path("sante", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("hors-ligne", views.offline, name="offline"),
    path("internal/cron/import", views.cron_import, name="cron-import"),
    path("internal/cron/daily", views.cron_daily, name="cron-daily"),
]
