from django import forms

from apps.catalog.models import Ingredient
from apps.catalog.text import stem_key
from apps.core.reference import Diet, MealType
from apps.core.reference import Equipment as EquipmentCode

from .models import (
    MAX_WEIGHT,
    WEIGHT_CRITERIA,
    Diner,
    DinerRestriction,
    Equipment,
    Household,
    HouseholdEquipment,
    HouseholdSettings,
)

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


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


WEIGHT_LABELS = {
    "taste": "Goûts",
    "rating": "Notes et favoris",
    "freshness": "Fraîcheur",
    "diversity": "Diversité",
    "antiwaste": "Anti-gaspillage",
    "budget": "Budget",
    "season": "Saison",
}


class SettingsForm(forms.ModelForm):
    """Réglages du moteur ; les poids (section avancée) restent vides pour garder les défauts."""

    meals = forms.MultipleChoiceField(
        label="Repas planifiés", choices=MealType.choices, widget=forms.CheckboxSelectMultiple
    )
    leftover_weekdays = forms.MultipleChoiceField(
        label="Jours « restes » (le déjeuner reprend le dîner de la veille)",
        choices=enumerate(WEEKDAYS),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = HouseholdSettings
        fields = [
            "meals",
            "max_minutes_weekday",
            "max_minutes_weekend",
            "budget_level",
            "leftover_weekdays",
            "min_repeat_days",
            "vegetarian_per_week",
            "source_mode",
            "cookeo_share",
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        weights = (self.instance.weights or {}) if self.instance.pk else {}
        for name in WEIGHT_CRITERIA:
            self.fields[f"weight_{name}"] = forms.IntegerField(
                label=f"Poids : {WEIGHT_LABELS[name]}",
                required=False,
                min_value=0,
                max_value=MAX_WEIGHT,
                initial=weights.get(name),
            )

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("source_mode")
        owned = HouseholdEquipment.objects.filter(
            household=self.instance.household, equipment_id=EquipmentCode.COOKEO.value
        )
        if mode and mode != HouseholdSettings.SourceMode.CLASSIC and not owned.exists():
            self.add_error("source_mode", "Le mode Cookeo exige l'équipement Cookeo dans le foyer.")
        return cleaned

    def clean_leftover_weekdays(self) -> list[int]:
        return [int(day) for day in self.cleaned_data["leftover_weekdays"]]

    def save(self, commit: bool = True):
        self.instance.weights = {
            name: self.cleaned_data[f"weight_{name}"]
            for name in WEIGHT_CRITERIA
            if self.cleaned_data.get(f"weight_{name}") is not None
        }
        return super().save(commit)


COMMON_TASTE_INGREDIENTS = (
    "poulet",
    "bœuf haché",
    "porc",
    "saumon",
    "thon",
    "crevettes",
    "jambon",
    "lardons",
    "saucisse",
    "œuf",
    "pâtes",
    "riz",
    "pomme de terre",
    "lentilles",
    "pois chiches",
    "carotte",
    "courgette",
    "tomate",
    "poivron",
    "aubergine",
    "champignon",
    "épinards",
    "brocoli",
    "chou-fleur",
    "haricots verts",
    "poireau",
    "oignon",
    "ail",
    "fromage râpé",
    "mozzarella",
    "fromage de chèvre",
    "crème fraîche",
    "yaourt nature",
    "avocat",
    "pomme",
    "banane",
    "fraise",
    "citron",
    "noix",
    "amandes",
    "chocolat noir",
    "coriandre",
    "basilic",
)


def taste_ingredients() -> list[Ingredient]:
    names = {stem_key(n) for n in COMMON_TASTE_INGREDIENTS}
    return [i for i in Ingredient.objects.order_by("name") if i.normalized_name in names]


class TasteForm(forms.Form):
    """Trois états par ingrédient : aime, neutre, n'aime pas (SPEC section 9, étape 4)."""

    likes = forms.ModelMultipleChoiceField(
        label="Aime", queryset=Ingredient.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip
    dislikes = forms.ModelMultipleChoiceField(
        label="N'aime pas", queryset=Ingredient.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        choices = Ingredient.objects.filter(pk__in=[i.pk for i in taste_ingredients()])
        self.fields["likes"].queryset = self.fields["dislikes"].queryset = choices

    def clean(self):
        cleaned = super().clean()
        both = set(cleaned.get("likes") or []) & set(cleaned.get("dislikes") or [])
        if both:
            raise forms.ValidationError("Un ingrédient ne peut pas être à la fois aimé et détesté.")
        return cleaned
