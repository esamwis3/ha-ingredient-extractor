"""Runtime state of a config entry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .providers.base import Provider
from .sorting import CategoryStore


@dataclass
class IngredientExtractorData:
    """Provider, target list and shared state for one config entry."""

    provider: Provider
    todo_entity: str
    categories: CategoryStore
    auto_sort: bool = True
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
