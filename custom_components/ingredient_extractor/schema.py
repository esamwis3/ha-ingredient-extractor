"""Prompt and JSON schema shared by every provider."""

from __future__ import annotations

from typing import Any

from .providers.base import Extraction, Ingredient, ProviderError

SYSTEM_PROMPT = """You read photos of recipes and list the ingredients a cook would need to buy.

Decide first whether the image shows a recipe or an ingredient list (printed, handwritten, \
on a screen, or a cookbook page). If it does not, return is_recipe=false and an empty list.

For a recipe, return every ingredient once, in the order written:
- quantity: the amount exactly as written, as digits where possible ("500", "2", "1/2", \
"1-2", "1.5"). Use "" if no amount is given.
- unit: the unit as written, in its short form: g, kg, ml, l, tsp, tbsp, cup, oz, lb, \
clove, pinch, tin, can, bunch, slice, handful. Use "" for countable items with no unit \
(e.g. "2 onions") or when there is no amount. Never calculate conversions yourself.
- name: the ingredient in plain lower-case words, keeping useful descriptors \
("plain flour", "unsalted butter", "red onions"). Drop preparation notes such as \
"finely chopped", "softened", "to serve", "divided". Use the plural when the quantity \
is more than one countable item.
- metric_quantity / metric_unit: if the same line also gives the amount in metric \
units (g, kg, ml, l), usually in brackets, copy that metric amount exactly as written \
("2 lbs (908 g) beef" -> quantity "2", unit "lb", metric_quantity "908", metric_unit "g"). \
Use "" for both when no metric amount is printed. Never calculate conversions yourself.

When the amount is a pack size ("400g tin chopped tomatoes", "2 x 400g tins chickpeas", \
"500ml carton stock"), use the total weight or volume as quantity and unit \
("400" "g", "800" "g", "500" "ml") and leave the container word out of the name.

Include items listed without an amount ("salt and pepper", "olive oil"), keeping \
items written together on one line as one item. Skip water. \
If the recipe has several sections (e.g. sauce, topping), include all of them. \
Never invent ingredients that are not visible."""

USER_PROMPT = "List the ingredients in this recipe image."

INGREDIENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_recipe": {"type": "boolean"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quantity": {"type": "string"},
                    "unit": {"type": "string"},
                    "name": {"type": "string"},
                    "metric_quantity": {"type": "string"},
                    "metric_unit": {"type": "string"},
                },
                "required": ["quantity", "unit", "name", "metric_quantity", "metric_unit"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["is_recipe", "ingredients"],
    "additionalProperties": False,
}


def parse_extraction(data: Any, max_items: int) -> Extraction:
    """Validate model JSON against the schema shape and build an Extraction."""
    if not isinstance(data, dict) or not isinstance(data.get("is_recipe"), bool):
        raise ProviderError("The AI returned an unexpected response")
    raw_items = data.get("ingredients")
    if not isinstance(raw_items, list):
        raise ProviderError("The AI returned an unexpected response")

    ingredients: list[Ingredient] = []
    for raw in raw_items[:max_items]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        quantity = str(raw.get("quantity") or "").strip() or None
        unit = str(raw.get("unit") or "").strip() or None
        metric_quantity = str(raw.get("metric_quantity") or "").strip() or None
        metric_unit = str(raw.get("metric_unit") or "").strip() or None
        ingredients.append(
            Ingredient(
                name=name,
                quantity=quantity,
                unit=unit,
                metric_quantity=metric_quantity,
                metric_unit=metric_unit,
            )
        )

    return Extraction(is_recipe=data["is_recipe"], ingredients=ingredients)
