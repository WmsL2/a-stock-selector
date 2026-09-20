"""Pure exact-rank descriptions over already-labeled selection research history."""

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime

from .research_effectiveness import (
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchHorizonEffectiveness,
)
from .research_return_history import SelectionResearchReturnHistory
from .research_returns import SelectionResearchReturnReport


class SelectionResearchRankEffectiveness(DomainModel):
    """Descriptive metrics for one exact official selection rank."""

    rank: int = Field(gt=0)
    observation_count: int = Field(gt=0)
    horizons: tuple[SelectionResearchHorizonEffectiveness, ...]

    @model_validator(mode="after")
    def exact_rank_metrics(self) -> "SelectionResearchRankEffectiveness":
        if tuple(item.horizon_sessions for item in self.horizons) != (5, 20, 60):
            raise ValueError("rank effectiveness horizons must retain fixed 5, 20, 60 order")
        if any(item.total_labels != self.observation_count for item in self.horizons):
            raise ValueError("rank horizon totals must equal rank observation count")
        return self


class SelectionResearchRankEffectivenessReport(DomainModel):
    """Exact-rank descriptive analysis of one existing return-label history."""

    schema_version: int = 1
    evaluated_at: datetime
    start_date: date | None
    end_date: date | None
    snapshot_count: int = Field(ge=0)
    empty_snapshot_count: int = Field(ge=0)
    item_observation_count: int = Field(ge=0)
    ranks: tuple[SelectionResearchRankEffectiveness, ...]

    @field_validator("evaluated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "evaluated_at")

    @model_validator(mode="after")
    def exact_report(self) -> "SelectionResearchRankEffectivenessReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research rank effectiveness schema version")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not follow end_date")
        if self.empty_snapshot_count > self.snapshot_count:
            raise ValueError("empty snapshots must not exceed snapshots")
        rank_values = tuple(item.rank for item in self.ranks)
        if rank_values != tuple(sorted(rank_values)):
            raise ValueError("rank effectiveness entries must be strictly ascending")
        if len(set(rank_values)) != len(rank_values):
            raise ValueError("rank effectiveness entries must be unique")
        if self.item_observation_count == 0 and self.ranks:
            raise ValueError("empty item observations require no rank entries")
        if self.item_observation_count > 0 and not self.ranks:
            raise ValueError("item observations require rank entries")
        if sum(item.observation_count for item in self.ranks) != self.item_observation_count:
            raise ValueError("rank observation counts must equal item observation count")
        if any(item.observation_count > self.snapshot_count for item in self.ranks):
            raise ValueError("rank observations must not exceed snapshots")
        return self


class SelectionResearchRankEffectivenessAnalyzer:
    """Delegate exact-rank label descriptions to the Task50 analyzer."""

    def __init__(self, effectiveness_analyzer: SelectionResearchEffectivenessAnalyzer | None = None) -> None:
        self._effectiveness_analyzer = effectiveness_analyzer or SelectionResearchEffectivenessAnalyzer()

    def analyze(
        self, history: SelectionResearchReturnHistory
    ) -> SelectionResearchRankEffectivenessReport:
        """Describe only the ranks actually persisted in the supplied history."""
        observed_ranks = sorted({item.rank for report in history.reports for item in report.items})
        rank_metrics = tuple(
            self._rank_effectiveness(history, rank)
            for rank in observed_ranks
        )
        return SelectionResearchRankEffectivenessReport(
            evaluated_at=history.evaluated_at,
            start_date=history.start_date,
            end_date=history.end_date,
            snapshot_count=len(history.reports),
            empty_snapshot_count=sum(not report.items for report in history.reports),
            item_observation_count=sum(len(report.items) for report in history.reports),
            ranks=rank_metrics,
        )

    def _rank_effectiveness(
        self, history: SelectionResearchReturnHistory, rank: int
    ) -> SelectionResearchRankEffectiveness:
        filtered_history = _filtered_history(history, rank)
        effectiveness = self._effectiveness_analyzer.analyze(filtered_history)
        return SelectionResearchRankEffectiveness(
            rank=rank,
            observation_count=effectiveness.item_observation_count,
            horizons=effectiveness.horizons,
        )


def _filtered_history(
    history: SelectionResearchReturnHistory, rank: int
) -> SelectionResearchReturnHistory:
    """Retain every snapshot while keeping only one exact rank in each report."""
    return SelectionResearchReturnHistory(
        evaluated_at=history.evaluated_at,
        start_date=history.start_date,
        end_date=history.end_date,
        reports=tuple(
            SelectionResearchReturnReport(
                snapshot_as_of=report.snapshot_as_of,
                evaluated_at=report.evaluated_at,
                anchor_date=report.anchor_date,
                items=tuple(item for item in report.items if item.rank == rank),
            )
            for report in history.reports
        ),
    )
