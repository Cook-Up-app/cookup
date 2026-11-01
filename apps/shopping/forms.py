from django import forms

from apps.catalog.models import Ingredient
from apps.core.reference import Aisle

from .models import PantryItem


class ItemForm(forms.Form):
    label = forms.CharField(
        label="Article",
        max_length=200,
        widget=forms.TextInput(
            attrs={"placeholder": "Ajouter un article…", "aria-label": "Article"}
        ),
    )
    quantity = forms.DecimalField(
        label="Quantité",
        required=False,
        min_value=0,
        max_digits=9,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"placeholder": "Quantité", "aria-label": "Quantité"}),
    )
    aisle = forms.ChoiceField(
        label="Rayon",
        choices=Aisle.choices,
        initial=Aisle.MISC,
        widget=forms.Select(attrs={"aria-label": "Rayon"}),
    )


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


class PantryBulkForm(forms.Form):
    """Cocher plusieurs produits toujours en stock, rayon par rayon, et tout enregistrer d'un coup.

    Les produits de base (sel, huile…) et ceux déjà au placard ne sont pas proposés.
    """

    FIELD_PREFIX = "aisle_"

    def __init__(self, *args, household, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        stocked = PantryItem.objects.for_household(household).values("ingredient_id")
        candidates = (
            Ingredient.objects.filter(is_staple=False)
            .exclude(pk__in=stocked)
            .order_by("name")
            .values_list("pk", "name", "aisle")
        )
        by_aisle: dict[str, list[tuple[str, str]]] = {code: [] for code in Aisle.values}
        for pk, name, aisle in candidates:
            by_aisle.setdefault(aisle, []).append((str(pk), name))
        for code, label in Aisle.choices:
            if by_aisle[code]:
                self.fields[self.FIELD_PREFIX + code] = forms.MultipleChoiceField(
                    label=str(label), choices=by_aisle[code], required=False,
                    widget=forms.CheckboxSelectMultiple,
                )  # fmt: skip

    def aisle_fields(self):
        return [self[name] for name in self.fields]

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(name) for name in self.fields):
            raise forms.ValidationError("Cochez au moins un produit.")
        return cleaned

    def selected_ids(self) -> list[int]:
        return [int(pk) for name in self.fields for pk in self.cleaned_data.get(name, [])]


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
