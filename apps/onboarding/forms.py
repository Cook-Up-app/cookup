"""Formulaires de l'assistant d'accueil : une question, un formulaire."""

from django import forms

from apps.catalog.models import Ingredient
from apps.core.reference import Allergen, Diet, MealType
from apps.households.forms import WEEKDAYS, taste_ingredients
from apps.households.models import Diner, Equipment

SERVINGS = [(str(n), str(n)) for n in range(1, 9)]
WEEKDAY_MINUTES = [
    ("15", "15 min"),
    ("30", "30 min"),
    ("45", "45 min"),
    ("60", "1 h"),
    ("90", "1 h 30"),
]
WEEKEND_MINUTES = [
    ("30", "30 min"),
    ("60", "1 h"),
    ("90", "1 h 30"),
    ("120", "2 h"),
    ("180", "3 h"),
]
BUDGETS = [("1", "Économique"), ("2", "Raisonnable"), ("3", "Confortable")]
TASTE_LIKE, TASTE_NEUTRAL, TASTE_DISLIKE = "1", "0", "-1"


class NameForm(forms.Form):
    name = forms.CharField(
        label="Nom du foyer",
        max_length=100,
        widget=forms.TextInput(attrs={"aria-label": "Nom du foyer", "autofocus": True}),
    )


class ServingsForm(forms.Form):
    servings = forms.ChoiceField(label="Personnes", choices=SERVINGS, widget=forms.RadioSelect)


class DinerAddForm(forms.ModelForm):
    class Meta:
        model = Diner
        fields = ["first_name", "age_group"]
        labels = {"age_group": "Tranche d'âge"}
        widgets = {"age_group": forms.RadioSelect}


class AllergiesForm(forms.Form):
    allergens = forms.MultipleChoiceField(
        label="Allergies strictes", choices=Allergen.choices, required=False,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip


class DietsForm(forms.Form):
    diets = forms.MultipleChoiceField(
        label="Régimes", choices=Diet.choices, required=False, widget=forms.CheckboxSelectMultiple
    )


class EquipmentStepForm(forms.Form):
    equipment = forms.ModelMultipleChoiceField(
        label="Équipements",
        queryset=Equipment.objects.order_by("label"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class MealsForm(forms.Form):
    meals = forms.MultipleChoiceField(
        label="Repas", choices=MealType.choices, widget=forms.CheckboxSelectMultiple
    )


class WeekdayMinutesForm(forms.Form):
    minutes = forms.ChoiceField(label="Temps", choices=WEEKDAY_MINUTES, widget=forms.RadioSelect)


class WeekendMinutesForm(forms.Form):
    minutes = forms.ChoiceField(label="Temps", choices=WEEKEND_MINUTES, widget=forms.RadioSelect)


class BudgetForm(forms.Form):
    budget = forms.ChoiceField(label="Budget", choices=BUDGETS, widget=forms.RadioSelect)


class LeftoversForm(forms.Form):
    days = forms.MultipleChoiceField(
        label="Jours « restes »",
        choices=list(enumerate(WEEKDAYS)),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class TriState(forms.RadioSelect):
    """Trois boutons côte à côte (j'aime, neutre, non) pour une ligne de liste."""

    template_name = "forms/tri_state.html"


class TastesForm(forms.Form):
    """Un choix à trois états par ingrédient courant : j'aime, neutre, je n'aime pas."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.ingredients: list[Ingredient] = taste_ingredients()
        for ingredient in self.ingredients:
            self.fields[f"i{ingredient.pk}"] = forms.ChoiceField(
                label=ingredient.name,
                required=False,
                initial=TASTE_NEUTRAL,
                choices=[(TASTE_LIKE, "J'aime"), (TASTE_NEUTRAL, "Neutre"), (TASTE_DISLIKE, "Non")],
                widget=TriState,
            )

    def choices(self) -> dict[Ingredient, str]:
        """Choix par ingrédient ; l'absence de réponse vaut neutre."""
        return {
            ingredient: self.cleaned_data.get(f"i{ingredient.pk}") or TASTE_NEUTRAL
            for ingredient in self.ingredients
        }
