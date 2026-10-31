from django import forms

from apps.core.reference import Diet

from .models import Diner, DinerRestriction, Equipment, Household


class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["name", "default_servings", "week_start_day"]


class InvitationForm(forms.Form):
    email = forms.EmailField(label="E-mail de la personne invitée")


class AcceptInvitationForm(forms.Form):
    display_name = forms.CharField(label="Nom affiché", max_length=100)
    password1 = forms.CharField(
        label="Mot de passe (12 caractères minimum)", widget=forms.PasswordInput
    )
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and password != cleaned.get("password2"):
            self.add_error("password2", "Les deux mots de passe ne correspondent pas.")
        return cleaned


class DinerForm(forms.ModelForm):
    diets = forms.MultipleChoiceField(
        label="Régimes", choices=Diet.choices, required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Diner
        fields = ["first_name", "age_group", "diets"]


class RestrictionForm(forms.ModelForm):
    class Meta:
        model = DinerRestriction
        fields = ["allergen", "ingredient_name", "severity"]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("allergen") and not cleaned.get("ingredient_name"):
            raise forms.ValidationError("Indiquez un allergène ou un ingrédient.")
        return cleaned


class EquipmentForm(forms.Form):
    equipment = forms.ModelMultipleChoiceField(
        label="Équipements disponibles",
        queryset=Equipment.objects.order_by("label"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
