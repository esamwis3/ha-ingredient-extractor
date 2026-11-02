"""Tests for ingredient formatting."""

from fractions import Fraction

import pytest

from custom_components.ingredient_extractor.formatting import (
    ParsedItem,
    format_item,
    item_key,
    merge_items,
    parse_item,
)
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


@pytest.mark.parametrize(
    ("name", "qty", "unit", "mqty", "munit", "expected"),
    [
        # Imperial weights/volumes and packs switch to the printed metric amount.
        ("ground beef", "2", "lbs", "908", "g", "908g ground beef"),
        ("macaroni", "10", "oz", "283", "g", "283g macaroni"),
        ("broth", "2", "cups", "480", "g", "480g broth"),
        ("milk", "1", "cup", "240", "ml", "240ml milk"),
        ("crushed tomatoes", "1", "can", "420", "g", "420g crushed tomatoes"),
        # Spoons and whole-item counts stay as written.
        ("chili powder", "2", "tbsp", "18", "g", "2 tbsp chili powder"),
        ("onion powder", "1", "tsp", "3", "g", "1 tsp onion powder"),
        ("red bell pepper", "1", "", "150", "g", "1 red bell pepper"),
        ("green onions", "1", "bunch", "100", "g", "1 bunch green onions"),
        # No metric printed, or nonsense metric: keep the original.
        ("butter", "1", "pound", "", "", "1 lb butter"),
        ("butter", "1", "lb", "about", "g", "1 lb butter"),
        ("butter", "1", "lb", "450", "stone", "1 lb butter"),
        # Stray punctuation returned as the unit is dropped.
        ("medium green bell pepper", "1", ",", "", "", "1 medium green bell pepper"),
        ("flour", "500", "(g)", "", "", "500g flour"),
    ],
)
def test_prefers_printed_metric(name, qty, unit, mqty, munit, expected):
    ing = Ingredient(
        name=name, quantity=qty, unit=unit, metric_quantity=mqty, metric_unit=munit
    )
    assert format_item(ing) == expected


@pytest.mark.parametrize(
    ("existing", "new", "expected"),
    [
        ("500g plain flour", "200g plain flour", "700g plain flour"),
        ("1kg mince", "500g mince", "1.5kg mince"),
        ("2l milk", "500ml milk", "2.5l milk"),
        ("milk", "500ml milk", "500ml milk"),
        ("500ml milk", "milk", "500ml milk"),
        ("milk", "milk", "milk"),
        ("1 onion", "2 onions", "3 onions"),
        ("1 lime", "1 lime", "2 limes"),
        ("2 cloves garlic", "1 clove garlic", "3 cloves garlic"),
        ("croissants x2", "2 croissants", "4 croissants"),
        ("1/2 tsp salt", "1/4 tsp salt", "3/4 tsp salt"),
        ("1 1/2 cups sugar", "1/2 cup sugar", "2 cups sugar"),
        ("2 tbsp olive oil", "100ml olive oil", None),
    ],
)
def test_merge_items(existing, new, expected) -> None:
    """Same-unit and metric amounts add up; a bare name adds nothing; mixed units don't merge."""
    assert merge_items(existing, new) == expected


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("500g Plain Flour", "plain flour", True),
        ("2 onions", "onion", True),
        ("tomatoes", "400g tomatoes", True),
        ("2 red onions", "onions", False),
        ("1-2 chillies", "1 chilli", False),
        ("potatoes (bag)", "potatoes", False),
    ],
)
def test_item_key(a, b, same) -> None:
    """Keys ignore amount, case and plural, but not descriptors."""
    assert (item_key(a) == item_key(b)) is same


def test_parse_item() -> None:
    """Units are only taken from known unit words."""
    assert parse_item("2 cloves garlic") == ParsedItem("garlic", Fraction(2), "clove")
    assert parse_item("2 red onions") == ParsedItem("red onions", Fraction(2))
    assert parse_item("1-2 chillies") == ParsedItem("1-2 chillies")
