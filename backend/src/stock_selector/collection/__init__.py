"""Explicit bounded daily-price collection primitives."""

from stock_selector.collection.daily import DailyPriceCollector
from stock_selector.collection.errors import (
    CollectionDataError,
    CollectionError,
    CollectionNotSupportedError,
)
from stock_selector.collection.fundamentals import (
    FinancialCollector,
    FundamentalsCollectionReport,
    IndustryCollector,
    ValuationCollector,
)
from stock_selector.collection.models import (
    DailyCollectionReport,
    DailyCollectionRequest,
    DailyCollectionStatus,
    DailySymbolCollectionResult,
)
from stock_selector.collection.risk import (
    CurrentRiskCollectionRequest,
    CurrentRiskCollectionResult,
    CurrentRiskStateCollector,
)
from stock_selector.collection.structural_fundamentals import (
    StructuralCoreCollectionReport,
    StructuralCoreCollectionRequest,
    StructuralCoreDomainStatus,
    StructuralCoreFundamentalsCollector,
    StructuralCoreSymbolResult,
)
from stock_selector.collection.structural_valuation import (
    StructuralValuationCollectionReport,
    StructuralValuationCollectionRequest,
    StructuralValuationCollector,
    StructuralValuationStatus,
    StructuralValuationSymbolResult,
)

__all__ = [
    "CollectionDataError",
    "CollectionError",
    "CollectionNotSupportedError",
    "CurrentRiskCollectionRequest",
    "CurrentRiskCollectionResult",
    "CurrentRiskStateCollector",
    "DailyCollectionReport",
    "DailyCollectionRequest",
    "DailyCollectionStatus",
    "DailyPriceCollector",
    "DailySymbolCollectionResult",
    "FinancialCollector",
    "FundamentalsCollectionReport",
    "IndustryCollector",
    "StructuralCoreCollectionReport",
    "StructuralCoreCollectionRequest",
    "StructuralCoreDomainStatus",
    "StructuralCoreFundamentalsCollector",
    "StructuralCoreSymbolResult",
    "StructuralValuationCollectionReport",
    "StructuralValuationCollectionRequest",
    "StructuralValuationCollector",
    "StructuralValuationStatus",
    "StructuralValuationSymbolResult",
    "ValuationCollector",
]
