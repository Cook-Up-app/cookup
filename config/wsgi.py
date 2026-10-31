"""Point d'entrée WSGI (référencé par `[tool.vercel] entrypoint`)."""

import os

from django.core.wsgi import get_wsgi_application

# Affectation directe, pas `setdefault` : cette entrée ne sert qu'en production, et une
# variable `DJANGO_SETTINGS_MODULE` héritée (par exemple `config.settings.local`, valeur
# par défaut de manage.py détectée par Vercel) ne doit jamais activer DEBUG en ligne.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"

application = get_wsgi_application()
