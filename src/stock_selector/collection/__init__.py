"""Explicit bounded daily-price collection primitives."""

from stock_selector.collection.daily import DailyPriceCollector
from stock_selector.collection.errors import (
    CollectionDataError,
    CollectionError,
    CollectionNotSupportedError,
)
from stock_selector.collection.models import (
    DailyCollectionReport,
    DailyCollectionRequest,
    DailyCollectionStatus,
    DailySymbolCollectionResult,
)

__all__ = [
    "CollectionDataError",
    "CollectionError",
    "CollectionNotSupportedError",
    "DailyCollectionReport",
    "DailyCollectionRequest",
    "DailyCollectionStatus",
    "DailyPriceCollector",
    "DailySymbolCollectionResult",
]
