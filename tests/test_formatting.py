"""Tests for ingredient formatting."""

import pytest

from custom_components.ingredient_extractor.formatting import format_item
from custom_components.ingredient_extractor.providers.base import Ingredient


@pytest.mark.parametrize(
    ("name", "qty", "unit", "expected"),
    [
        ("plain flour", "500", "g", "500g plain flour"),
        ("plain flour", "500", "grams", "500g plain flour"),
        ("sugar", "1", "kilograms", "1kg sugar"),
        ("milk", "250", "millilitres", "250ml milk"),
        ("milk", "1", "Litres", "1l milk"),
        ("salt", "1", "teaspoons", "1 tsp salt"),
        ("olive oil", "2", "tbsp", "2 tbsp olive oil"),
        ("olive oil", "2", "Tablespoons.", "2 tbsp olive oil"),
        ("cheese", "4", "oz", "4 oz cheese"),
        ("butter", "1", "pound", "1 lb butter"),
        ("garlic", "2", "clove", "2 cloves garlic"),
        ("garlic", "1", "clove", "1 clove garlic"),
        ("garlic", "1-2", "cloves", "1-2 cloves garlic"),
        ("milk", "1", "cup", "1 cup milk"),
        ("sugar", "1/2", "cup", "1/2 cup sugar"),
        ("sugar", "1 1/2", "cups", "1 1/2 cups sugar"),
        ("flour", "1.5", "cup", "1.5 cups flour"),
        ("parsley", "2", "bunch", "2 bunches parsley"),
        ("saffron", "1", "pinch", "1 pinch saffron"),
        ("tomatoes", "2", "tin", "2 tins tomatoes"),
        ("onions", "2", "", "2 onions"),
        ("salt and pepper", "", "", "salt and pepper"),
        ("salt", None, "tsp", "salt"),
        ("sauce", "3", "Dashes", "3 dashes sauce"),
        ("  red   onions ", " 2 ", None, "2 red onions"),
    ],
)
def test_format_item(name, qty, unit, expected):
    """Formatting follows the contract."""
    assert format_item(Ingredient(name=name, quantity=qty, unit=unit)) == expected


def test_item_capped_at_255():
    """Very long names are truncated."""
    assert len(format_item(Ingredient(name="x" * 400, quantity="1"))) == 255
