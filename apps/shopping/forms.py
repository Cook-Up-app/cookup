from django import forms

from apps.catalog.models import Ingredient
from apps.core.reference import Aisle

from .models import PantryItem


class ItemForm(forms.Form):
    label = forms.CharField(label="Article", max_length=200)
    quantity = forms.DecimalField(
        label="Quantité", required=False, min_value=0, max_digits=9, decimal_places=2
    )
    aisle = forms.ChoiceField(label="Rayon", choices=Aisle.choices, initial=Aisle.MISC)


class PantryForm(forms.ModelForm):
    ingredient = forms.ModelChoiceField(
        label="Ingrédient", queryset=Ingredient.objects.order_by("name")
    )
    quantity = forms.DecimalField(
        label="Quantité disponible (en g, ml ou pièces, facultatif)",
        required=False, min_value=0, max_digits=9, decimal_places=2,
    )  # fmt: skip

    class Meta:
        model = PantryItem
        fields = ["ingredient", "always_in_stock", "quantity"]
        labels = {"always_in_stock": "Toujours en stock (jamais dans la liste)"}


class AisleOrderForm(forms.Form):
    """Un rang par rayon ; l'ordre résultant est mémorisé pour le foyer."""

    def __init__(self, *args, current: list[str], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.current = current
        for rank, aisle in enumerate(current, start=1):
            self.fields[aisle] = forms.IntegerField(
                label=str(Aisle(aisle).label), min_value=1, max_value=len(current), initial=rank
            )

    def ordered(self) -> list[str]:
        ranks = self.cleaned_data
        return sorted(self.current, key=lambda aisle: (ranks[aisle], self.current.index(aisle)))
