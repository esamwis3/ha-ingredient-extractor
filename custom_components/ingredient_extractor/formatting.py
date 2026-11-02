"""Turn extracted ingredients into shopping-list item text."""

from __future__ import annotations

from dataclasses import dataclass
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
# Imperial weights/volumes and packs: swap for the printed metric amount when there is one.
# Spoons and whole-item counts are kept as written.
_PREFER_METRIC = frozenset({"lb", "oz", "cup", "pint", "quart", "stick", "tin", "can"})
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
    # Models occasionally return stray punctuation (",", "()") as the unit.
    key = unit.strip().lower().strip(".,;:()[] ")
    return UNIT_ALIASES.get(key, key)


def format_item(ing: Ingredient) -> str:
    """Return e.g. "500g plain flour", "2 cloves garlic", "2 onions"."""
    name = " ".join(ing.name.split())
    quantity = " ".join((ing.quantity or "").split())
    unit = _normalise_unit(ing.unit or "") if quantity else ""
    metric_quantity = " ".join((ing.metric_quantity or "").split())
    metric_unit = _normalise_unit(ing.metric_unit or "")
    if (
        unit in _PREFER_METRIC
        and metric_quantity
        and metric_unit in _TIGHT_UNITS
        and _quantity_value(metric_quantity) is not None
    ):
        quantity, unit = metric_quantity, metric_unit

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


# --- Reading item text back, to combine duplicates --------------------------------

_KNOWN_UNITS = (
    frozenset(UNIT_ALIASES.values())
    | _TIGHT_UNITS
    | _COUNTABLE
    | {"tsp", "tbsp", "oz", "lb", "pint", "quart"}
)
# Units that convert into each other: unit -> (family, size in the family's base unit).
_CONVERTIBLE: dict[str, tuple[str, int]] = {
    "g": ("g", 1), "kg": ("g", 1000),
    "ml": ("ml", 1), "cl": ("ml", 10), "l": ("ml", 1000),
}  # fmt: skip
_LARGE_UNIT = {"g": "kg", "ml": "l"}
# Fractions first so "1/2" is not read as "1"; a range ("1-2") is not a quantity.
_QTY = r"(?:\d+/\d+|\d+(?:\.\d+)?(?:\s+\d+/\d+)?)(?![-–/.\d])"
_LEADING_QTY_RE = re.compile(rf"^(?P<qty>{_QTY})\s*(?:[x×]\s+)?(?P<rest>.+)$", re.IGNORECASE)
_TRAILING_COUNT_RE = re.compile(r"^(?P<rest>.+?)\s*[x×]\s*(?P<qty>\d+)\.?$", re.IGNORECASE)
_UNIT_RE = re.compile(r"^(?P<unit>[a-z]+)\.?(?:\s+|$)(?P<name>.*)$", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\w\s]")


@dataclass(frozen=True, slots=True)
class ParsedItem:
    """Item text split into amount and name ("500g plain flour")."""

    name: str
    quantity: Fraction | None = None
    unit: str = ""


def _parse_quantity(text: str) -> Fraction | None:
    try:
        return sum((Fraction(part) for part in text.split()), Fraction(0))
    except (ValueError, ZeroDivisionError):
        return None


def parse_item(text: str) -> ParsedItem:
    """Split shopping-list text into quantity, unit and name. Ranges are left in the name."""
    text = " ".join(text.split())
    if match := _TRAILING_COUNT_RE.match(text):
        return ParsedItem(match["rest"], Fraction(int(match["qty"])))
    match = _LEADING_QTY_RE.match(text)
    if not match or (quantity := _parse_quantity(match["qty"])) is None:
        return ParsedItem(text)
    rest = match["rest"]
    if unit_match := _UNIT_RE.match(rest):
        unit = _normalise_unit(unit_match["unit"])
        if unit in _KNOWN_UNITS and unit_match["name"]:
            return ParsedItem(unit_match["name"], quantity, unit)
    return ParsedItem(rest, quantity)


def _singular(word: str) -> str:
    if word.endswith("oes") or word.endswith("ches") or word.endswith("shes"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def item_key(text: str) -> str:
    """Name used to spot the same item twice: no amount, case, punctuation or plural."""
    words = _NON_WORD_RE.sub(" ", parse_item(text).name.lower()).split()
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def _format_quantity(value: Fraction, unit: str) -> str:
    whole, part = divmod(value, 1)
    if not part:
        return str(whole)
    if unit not in _TIGHT_UNITS and part.denominator in (2, 3, 4, 8):
        return f"{whole} {part}" if whole else str(part)
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def merge_items(existing: str, new: str) -> str | None:
    """Text for one entry covering both, or None if the amounts can't be added up.

    Returns `existing` unchanged when the new entry adds nothing ("milk" + "milk").
    """
    old, add = parse_item(existing), parse_item(new)
    if add.quantity is None:
        return existing
    if old.quantity is None:
        return new
    if old.unit == add.unit:
        unit, total = old.unit, old.quantity + add.quantity
    elif (a := _CONVERTIBLE.get(old.unit)) and (b := _CONVERTIBLE.get(add.unit)) and a[0] == b[0]:
        unit, total = a[0], old.quantity * a[1] + add.quantity * b[1]
        # "1kg" + "500g" reads better as "1.5kg" than "1500g".
        if _LARGE_UNIT[unit] in (old.unit, add.unit) and total >= 1000 and not total % 10:
            unit, total = _LARGE_UNIT[unit], total / 1000
    else:
        return None

    name = old.name
    if not unit and total > 1:
        # Countable item: keep whichever spelling is plural, else add an "s".
        name = next(
            (n for n in (old.name, add.name) if n.lower().endswith("s")), old.name + "s"
        )
    return format_item(Ingredient(name=name, quantity=_format_quantity(total, unit), unit=unit))
