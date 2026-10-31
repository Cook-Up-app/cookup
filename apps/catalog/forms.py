from django import forms

from apps.core.reference import MealType, RecipeSource

from .dto import RecipeDTO
from .models import Recipe

MAX_LINES = 80


class SearchForm(forms.Form):
    q = forms.CharField(label="Recherche", required=False, max_length=100)
    max_minutes = forms.IntegerField(
        label="Temps max (min)", required=False, min_value=5, max_value=600
    )
    meal_type = forms.ChoiceField(
        label="Repas", required=False, choices=[("", "Tous"), *MealType.choices]
    )
    source = forms.ChoiceField(
        label="Source", required=False, choices=[("", "Toutes"), *RecipeSource.choices]
    )
    cookeo_only = forms.BooleanField(label="Compatible Cookeo", required=False)


class FeedbackForm(forms.Form):
    """Avis du foyer : note, favori, exclusion (alimente le moteur de menus)."""

    rating = forms.TypedChoiceField(
        label="Note",
        required=False,
        coerce=int,
        empty_value=None,
        choices=[("", "Pas de note"), *((str(n), f"{n} / 5") for n in range(1, 6))],
    )
    favorite = forms.BooleanField(label="Favori", required=False)
    excluded = forms.BooleanField(label="Ne plus me proposer cette recette", required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("favorite") and cleaned.get("excluded"):
            raise forms.ValidationError(
                "Une recette ne peut pas être à la fois favorite et exclue."
            )
        return cleaned


class ImportUrlForm(forms.Form):
    url = forms.URLField(label="Adresse de la recette", max_length=500, assume_scheme="https")


class ManualRecipeForm(forms.Form):
    title = forms.CharField(label="Titre", max_length=200)
    servings = forms.IntegerField(label="Portions", min_value=1, max_value=50, initial=4)
    prep_minutes = forms.IntegerField(
        label="Préparation (min)", required=False, min_value=0, max_value=1000
    )
    cook_minutes = forms.IntegerField(
        label="Cuisson (min)", required=False, min_value=0, max_value=1000
    )
    meal_types = forms.MultipleChoiceField(
        label="Repas", choices=MealType.choices, widget=forms.CheckboxSelectMultiple
    )
    tags = forms.CharField(
        label="Étiquettes (séparées par des virgules)", required=False, max_length=200
    )
    ingredients = forms.CharField(
        label="Ingrédients (un par ligne)", widget=forms.Textarea(attrs={"rows": 8})
    )
    steps = forms.CharField(
        label="Étapes (une par ligne)", widget=forms.Textarea(attrs={"rows": 8})
    )

    @staticmethod
    def _lines(text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > MAX_LINES:
            raise forms.ValidationError(f"{MAX_LINES} lignes au maximum.")
        return lines

    def clean_ingredients(self) -> list[str]:
        lines = self._lines(self.cleaned_data["ingredients"])
        if not lines:
            raise forms.ValidationError("Indiquez au moins un ingrédient.")
        return lines

    def clean_steps(self) -> list[str]:
        return self._lines(self.cleaned_data["steps"])

    def to_dto(self) -> RecipeDTO:
        data = self.cleaned_data
        tags = [tag.strip().lower() for tag in data["tags"].split(",") if tag.strip()]
        return RecipeDTO(
            source=RecipeSource.MANUAL.value,
            title=data["title"].strip(),
            ingredient_lines=data["ingredients"],
            steps=data["steps"],
            servings=data["servings"],
            prep_minutes=data["prep_minutes"],
            cook_minutes=data["cook_minutes"],
            tags=tags[:12],
            meal_types=data["meal_types"],
        )


__all__ = ["ImportUrlForm", "ManualRecipeForm", "Recipe", "SearchForm"]
