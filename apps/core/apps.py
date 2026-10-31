from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _enable_rls(sender, using: str, **kwargs) -> None:
    from .rls import enable_rls_on_all_tables

    enable_rls_on_all_tables(using)


class CoreConfig(AppConfig):
    name = "apps.core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Après chaque `migrate` : couvre aussi les tables créées par les jalons suivants.
        post_migrate.connect(_enable_rls, sender=self, dispatch_uid="core.enable_rls")
