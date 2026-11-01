"""Turn extracted ingredients into shopping-list item text."""

from __future__ import annotations

from fractions import Fraction
import re

from .providers.base import Ingredient

MAX_ITEM_LENGTH = 255

UNIT_ALIASES: dict[str, str] = {
    "gram": "g", "grams": "g", "gr": "g",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
    "milligram": "mg", "milligrams": "mg",
    "millilitre": "ml", "millilitres": "ml", "milliliter": "ml",
    "milliliters": "ml", "mls": "ml",
    "centilitre": "cl", "centilitres": "cl",
    "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsps": "tbsp", "tbs": "tbsp",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    # Plural forms of countable units fold to the singular; we re-pluralise below.
    "cups": "cup", "cloves": "clove", "tins": "tin", "cans": "can",
    "bunches": "bunch", "slices": "slice", "handfuls": "handful",
    "pinches": "pinch", "sprigs": "sprig", "sticks": "stick",
}  # fmt: skip

# Joined to the number with no space ("500g").
_TIGHT_UNITS = frozenset({"g", "kg", "mg", "ml", "l", "cl"})
_PLURALS = {"bunch": "bunches", "pinch": "pinches"}
_COUNTABLE = frozenset(
    {"cup", "clove", "tin", "can", "bunch", "slice", "handful", "pinch", "sprig", "stick"}
)


def _quantity_value(quantity: str) -> float | None:
    """Best-effort numeric value; ranges ("1-2") count as their upper bound."""
    text = quantity.replace("–", "-").replace("—", "-")
    try:
        if "-" in text:
            text = text.rsplit("-", 1)[1]
        return float(sum(Fraction(part) for part in text.split()))
    except (ValueError, ZeroDivisionError):
        return None


def _normalise_unit(unit: str) -> str:
    key = unit.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(key, key)


def format_item(ing: Ingredient) -> str:
    """Return e.g. "500g plain flour", "2 cloves garlic", "2 onions"."""
    name = " ".join(ing.name.split())
    quantity = " ".join((ing.quantity or "").split())
    unit = _normalise_unit(ing.unit or "") if quantity else ""

    if not quantity:
        text = name
    elif not unit:
        text = f"{quantity} {name}"
    else:
        if unit in _COUNTABLE:
            value = _quantity_value(quantity)
            if value is not None and value > 1:
                unit = _PLURALS.get(unit, unit + "s")
        sep = "" if unit in _TIGHT_UNITS else " "
        text = f"{quantity}{sep}{unit} {name}"
    return text[:MAX_ITEM_LENGTH].rstrip()
