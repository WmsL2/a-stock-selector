"""Local, selective persistence for validated market-domain records."""

from stock_selector.storage.errors import StorageDataError, StorageError, StorageIOError
from stock_selector.storage.repository import (
    AdjustedReturnStorageStats,
    LocalMarketRepository,
    StorageStats,
)

__all__ = [
    "AdjustedReturnStorageStats",
    "LocalMarketRepository",
    "StorageDataError",
    "StorageError",
    "StorageIOError",
    "StorageStats",
]
