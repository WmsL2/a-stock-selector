"""Invariant tests for immutable structural universe output models."""

from datetime import date

import pytest
from pydantic import ValidationError

from stock_selector.universe.models import (
    UniverseDecision,
    UniverseExclusionReason,
    UniverseSnapshot,
)


def test_universe_decision_requires_reasons_to_match_membership() -> None:
    with pytest.raises(ValidationError):
        UniverseDecision(
            symbol="600519.SH",
            included=True,
            reasons=(UniverseExclusionReason.BOARD_DISABLED,),
        )
    with pytest.raises(ValidationError):
        UniverseDecision(symbol="600519.SH", included=False)


def test_universe_snapshot_requires_sorted_complete_audit_trail() -> None:
    included = UniverseDecision(symbol="000001.SZ", included=True)
    excluded = UniverseDecision(
        symbol="600519.SH",
        included=False,
        reasons=(UniverseExclusionReason.DELISTED,),
    )
    snapshot = UniverseSnapshot(
        as_of=date(2025, 1, 1),
        input_count=2,
        members=("000001.SZ",),
        decisions=(included, excluded),
    )
    assert snapshot.members == ("000001.SZ",)
    with pytest.raises(ValidationError):
        UniverseSnapshot(
            as_of=date(2025, 1, 1),
            input_count=2,
            members=("600519.SH",),
            decisions=(included, excluded),
        )
