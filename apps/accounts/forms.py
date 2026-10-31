from django import forms
from django.http import HttpRequest

from .models import User

DISPLAY_NAME_MAX = User._meta.get_field("display_name").max_length


class SignupForm(forms.Form):
    """Champ ajouté au formulaire d'inscription d'allauth ; le foyer naît à la première visite."""

    display_name = forms.CharField(label="Prénom ou pseudo", max_length=DISPLAY_NAME_MAX)

    def signup(self, request: HttpRequest, user: User) -> None:
        user.display_name = self.cleaned_data["display_name"].strip()
        user.save(update_fields=["display_name"])
