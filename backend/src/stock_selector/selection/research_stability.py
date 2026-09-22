"""Pure, deterministic stability analysis for canonical selection snapshots."""

from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise

from pydantic import model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime

from .models import SelectionBlocker
from .research import SelectionResearchSnapshot


class SelectionResearchStabilityComparisonBlocker(StrEnum):
    PREVIOUS_SELECTION_BLOCKED = "previous_selection_blocked"
    CURRENT_SELECTION_BLOCKED = "current_selection_blocked"
    STRATEGY_CHANGED = "strategy_changed"


class SelectionResearchRankMovementStatus(StrEnum):
    RETAINED = "retained"
    ENTERED = "entered"
    EXITED = "exited"


class SelectionResearchRankMovement(DomainModel):
    symbol: str
    name: str
    status: SelectionResearchRankMovementStatus
    previous_rank: int | None
    current_rank: int | None
    rank_change: int | None

    @model_validator(mode="after")
    def valid_rank_fields(self) -> "SelectionResearchRankMovement":
        if self.status is SelectionResearchRankMovementStatus.RETAINED:
            if self.previous_rank is None or self.current_rank is None:
                raise ValueError("retained movement requires both official ranks")
            if self.rank_change != self.previous_rank - self.current_rank:
                raise ValueError("retained movement rank change must use official ranks")
        elif self.status is SelectionResearchRankMovementStatus.ENTERED:
            if self.previous_rank is not None or self.current_rank is None or self.rank_change is not None:
                raise ValueError("entered movement may only have a current official rank")
        elif self.previous_rank is None or self.current_rank is not None or self.rank_change is not None:
            raise ValueError("exited movement may only have a previous official rank")
        return self


class SelectionResearchStabilityTransition(DomainModel):
    previous_as_of: datetime
    current_as_of: datetime
    previous_strategy_name: str
    current_strategy_name: str
    previous_selection_ready: bool
    current_selection_ready: bool
    previous_blockers: tuple[SelectionBlocker, ...]
    current_blockers: tuple[SelectionBlocker, ...]
    comparable: bool
    comparison_blockers: tuple[SelectionResearchStabilityComparisonBlocker, ...]
    previous_item_count: int
    current_item_count: int
    retained_count: int | None
    entered_count: int | None
    exited_count: int | None
    retention_rate: float | None
    overlap_rate: float | None
    movements: tuple[SelectionResearchRankMovement, ...]

    @model_validator(mode="after")
    def valid_transition(self) -> "SelectionResearchStabilityTransition":
        ensure_aware_datetime(self.previous_as_of, "previous_as_of")
        ensure_aware_datetime(self.current_as_of, "current_as_of")
        if self.previous_as_of >= self.current_as_of:
            raise ValueError("stability transition timestamps must be chronological")
        expected_blockers: list[SelectionResearchStabilityComparisonBlocker] = []
        if not self.previous_selection_ready:
            expected_blockers.append(SelectionResearchStabilityComparisonBlocker.PREVIOUS_SELECTION_BLOCKED)
        if not self.current_selection_ready:
            expected_blockers.append(SelectionResearchStabilityComparisonBlocker.CURRENT_SELECTION_BLOCKED)
        if self.previous_strategy_name != self.current_strategy_name:
            expected_blockers.append(SelectionResearchStabilityComparisonBlocker.STRATEGY_CHANGED)
        if tuple(expected_blockers) != self.comparison_blockers:
            raise ValueError("comparison blockers must reflect official snapshot facts")
        if self.comparable != (not self.comparison_blockers):
            raise ValueError("comparability must match comparison blockers")
        derived = (self.retained_count, self.entered_count, self.exited_count, self.retention_rate, self.overlap_rate)
        if not self.comparable:
            if any(value is not None for value in derived) or self.movements:
                raise ValueError("unavailable stability analysis may not contain derived values")
            return self
        if any(value is None for value in derived):
            raise ValueError("comparable transition requires all derived values")
        assert self.retained_count is not None
        assert self.entered_count is not None
        assert self.exited_count is not None
        assert self.retention_rate is not None
        assert self.overlap_rate is not None
        if self.retained_count + self.exited_count != self.previous_item_count:
            raise ValueError("stability counts must partition previous items")
        if self.retained_count + self.entered_count != self.current_item_count:
            raise ValueError("stability counts must partition current items")
        if self.retention_rate != self.retained_count / self.previous_item_count:
            raise ValueError("retention rate must match official counts")
        denominator = self.retained_count + self.entered_count + self.exited_count
        if self.overlap_rate != self.retained_count / denominator:
            raise ValueError("overlap rate must match official counts")
        statuses = [movement.status for movement in self.movements]
        if statuses.count(SelectionResearchRankMovementStatus.RETAINED) != self.retained_count:
            raise ValueError("retained movements must match retained count")
        if statuses.count(SelectionResearchRankMovementStatus.ENTERED) != self.entered_count:
            raise ValueError("entered movements must match entered count")
        if statuses.count(SelectionResearchRankMovementStatus.EXITED) != self.exited_count:
            raise ValueError("exited movements must match exited count")
        return self


class SelectionResearchStabilityReport(DomainModel):
    schema_version: int = 1
    start_date: date | None
    end_date: date | None
    snapshot_count: int
    transition_count: int
    comparable_transition_count: int
    transitions: tuple[SelectionResearchStabilityTransition, ...]

    @model_validator(mode="after")
    def valid_report(self) -> "SelectionResearchStabilityReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research stability schema version")
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("start_date must not follow end_date")
        if self.transition_count != max(self.snapshot_count - 1, 0):
            raise ValueError("transition count must follow snapshot count")
        if self.transition_count != len(self.transitions):
            raise ValueError("transition count must match transitions")
        if self.comparable_transition_count != sum(item.comparable for item in self.transitions):
            raise ValueError("comparable transition count must match transitions")
        return self


class SelectionResearchStabilityAnalyzer:
    """Compare adjacent supplied canonical snapshots without changing their order."""

    def analyze(
        self,
        snapshots: tuple[SelectionResearchSnapshot, ...],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> SelectionResearchStabilityReport:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start_date must not follow end_date")
        if any(left.as_of >= right.as_of for left, right in pairwise(snapshots)):
            raise ValueError("selection research snapshots must be chronological")
        filtered = tuple(
            snapshot
            for snapshot in snapshots
            if (start_date is None or snapshot.as_of.date() >= start_date)
            and (end_date is None or snapshot.as_of.date() <= end_date)
        )
        transitions = tuple(
            self._transition(previous, current)
            for previous, current in pairwise(filtered)
        )
        return SelectionResearchStabilityReport(
            start_date=start_date,
            end_date=end_date,
            snapshot_count=len(filtered),
            transition_count=len(transitions),
            comparable_transition_count=sum(item.comparable for item in transitions),
            transitions=transitions,
        )

    def _transition(
        self,
        previous: SelectionResearchSnapshot,
        current: SelectionResearchSnapshot,
    ) -> SelectionResearchStabilityTransition:
        blockers: list[SelectionResearchStabilityComparisonBlocker] = []
        if not previous.selection_ready:
            blockers.append(SelectionResearchStabilityComparisonBlocker.PREVIOUS_SELECTION_BLOCKED)
        if not current.selection_ready:
            blockers.append(SelectionResearchStabilityComparisonBlocker.CURRENT_SELECTION_BLOCKED)
        if previous.strategy_name != current.strategy_name:
            blockers.append(SelectionResearchStabilityComparisonBlocker.STRATEGY_CHANGED)
        if blockers:
            return SelectionResearchStabilityTransition(
                previous_as_of=previous.as_of,
                current_as_of=current.as_of,
                previous_strategy_name=previous.strategy_name,
                current_strategy_name=current.strategy_name,
                previous_selection_ready=previous.selection_ready,
                current_selection_ready=current.selection_ready,
                previous_blockers=previous.blockers,
                current_blockers=current.blockers,
                comparable=False,
                comparison_blockers=tuple(blockers),
                previous_item_count=len(previous.items),
                current_item_count=len(current.items),
                retained_count=None,
                entered_count=None,
                exited_count=None,
                retention_rate=None,
                overlap_rate=None,
                movements=(),
            )
        previous_by_symbol = {item.symbol: item for item in previous.items}
        current_symbols = {item.symbol for item in current.items}
        movements: list[SelectionResearchRankMovement] = []
        retained_count = 0
        entered_count = 0
        for item in current.items:
            before = previous_by_symbol.get(item.symbol)
            if before is None:
                entered_count += 1
                movements.append(SelectionResearchRankMovement(
                    symbol=item.symbol,
                    name=item.name,
                    status=SelectionResearchRankMovementStatus.ENTERED,
                    previous_rank=None,
                    current_rank=item.rank,
                    rank_change=None,
                ))
            else:
                retained_count += 1
                movements.append(SelectionResearchRankMovement(
                    symbol=item.symbol,
                    name=item.name,
                    status=SelectionResearchRankMovementStatus.RETAINED,
                    previous_rank=before.rank,
                    current_rank=item.rank,
                    rank_change=before.rank - item.rank,
                ))
        exited_count = 0
        for item in previous.items:
            if item.symbol not in current_symbols:
                exited_count += 1
                movements.append(SelectionResearchRankMovement(
                    symbol=item.symbol,
                    name=item.name,
                    status=SelectionResearchRankMovementStatus.EXITED,
                    previous_rank=item.rank,
                    current_rank=None,
                    rank_change=None,
                ))
        return SelectionResearchStabilityTransition(
            previous_as_of=previous.as_of,
            current_as_of=current.as_of,
            previous_strategy_name=previous.strategy_name,
            current_strategy_name=current.strategy_name,
            previous_selection_ready=previous.selection_ready,
            current_selection_ready=current.selection_ready,
            previous_blockers=previous.blockers,
            current_blockers=current.blockers,
            comparable=True,
            comparison_blockers=(),
            previous_item_count=len(previous.items),
            current_item_count=len(current.items),
            retained_count=retained_count,
            entered_count=entered_count,
            exited_count=exited_count,
            retention_rate=retained_count / len(previous.items),
            overlap_rate=retained_count / (retained_count + entered_count + exited_count),
            movements=tuple(movements),
        )
