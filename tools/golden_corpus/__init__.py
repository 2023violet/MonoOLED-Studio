"""V1 golden corpus categories, in generation order."""
from __future__ import annotations

from importlib import import_module

from .common import Category

MODULES: tuple[str, ...] = ('encoding', 'formatting', 'raster', 'scenes', 'projects')

CATEGORIES: list[Category] = [
    Category(module.NAME, module.build, module.SOURCES)
    for module in (import_module(f'{__name__}.{name}') for name in MODULES)
]
