"""Pure cumulative exact-rank-cutoff descriptions of selection research history."""

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime

from .research_effectiveness import (
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchHorizonEffectiveness,
)
from .research_return_history import SelectionResearchReturnHistory
from .research_returns import SelectionResearchReturnReport


class SelectionResearchRankCutoffEffectiveness(DomainModel):
    """Descriptive metrics for one observed cumulative official-rank cutoff."""

    cutoff_rank: int = Field(gt=0)
    included_ranks: tuple[int, ...]
    observation_count: int = Field(gt=0)
    horizons: tuple[SelectionResearchHorizonEffectiveness, ...]

    @model_validator(mode="after")
    def exact_cutoff_metrics(self) -> "SelectionResearchRankCutoffEffectiveness":
        if not self.included_ranks:
            raise ValueError("cutoff included ranks must not be empty")
        if any(rank <= 0 for rank in self.included_ranks):
            raise ValueError("cutoff included ranks must be positive")
        if self.included_ranks != tuple(sorted(self.included_ranks)):
            raise ValueError("cutoff included ranks must be strictly ascending")
        if len(set(self.included_ranks)) != len(self.included_ranks):
            raise ValueError("cutoff included ranks must be unique")
        if self.included_ranks[-1] != self.cutoff_rank:
            raise ValueError("cutoff included ranks must end at cutoff rank")
        if tuple(item.horizon_sessions for item in self.horizons) != (5, 20, 60):
            raise ValueError("cutoff horizons must retain fixed 5, 20, 60 order")
        if any(item.total_labels != self.observation_count for item in self.horizons):
            raise ValueError("cutoff horizon totals must equal cutoff observation count")
        return self


class SelectionResearchRankCutoffEffectivenessReport(DomainModel):
    """Cumulative exact-rank-cutoff description of one existing label history."""

    schema_version: int = 1
    evaluated_at: datetime
    start_date: date | None
    end_date: date | None
    snapshot_count: int = Field(ge=0)
    empty_snapshot_count: int = Field(ge=0)
    item_observation_count: int = Field(ge=0)
    cutoffs: tuple[SelectionResearchRankCutoffEffectiveness, ...]

    @field_validator("evaluated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "evaluated_at")

    @model_validator(mode="after")
    def exact_report(self) -> "SelectionResearchRankCutoffEffectivenessReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research rank cutoff schema version")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not follow end_date")
        if self.empty_snapshot_count > self.snapshot_count:
            raise ValueError("empty snapshots must not exceed snapshots")
        cutoff_values = tuple(item.cutoff_rank for item in self.cutoffs)
        if cutoff_values != tuple(sorted(cutoff_values)):
            raise ValueError("cutoff ranks must be strictly ascending")
        if len(set(cutoff_values)) != len(cutoff_values):
            raise ValueError("cutoff ranks must be unique")
        expected_prefix: tuple[int, ...] = ()
        for cutoff in self.cutoffs:
            expected_prefix += (cutoff.cutoff_rank,)
            if cutoff.included_ranks != expected_prefix:
                raise ValueError("cutoff included ranks must be cumulative observed-rank prefixes")
        observations = tuple(item.observation_count for item in self.cutoffs)
        if observations != tuple(sorted(observations)):
            raise ValueError("cutoff observation counts must be nondecreasing")
        if self.item_observation_count == 0 and self.cutoffs:
            raise ValueError("empty item observations require no cutoffs")
        if self.item_observation_count > 0 and not self.cutoffs:
            raise ValueError("item observations require cutoffs")
        if self.cutoffs and observations[-1] != self.item_observation_count:
            raise ValueError("final cutoff observations must equal item observation count")
        return self


class SelectionResearchRankCutoffEffectivenessAnalyzer:
    """Delegate cumulative observed-cutoff descriptions to the Task50 analyzer."""

    def __init__(
        self,
        effectiveness_analyzer: SelectionResearchEffectivenessAnalyzer | None = None,
    ) -> None:
        self._effectiveness_analyzer = (
            effectiveness_analyzer or SelectionResearchEffectivenessAnalyzer()
        )

    def analyze(
        self, history: SelectionResearchReturnHistory
    ) -> SelectionResearchRankCutoffEffectivenessReport:
        """Describe each observed rank cutoff while retaining original history metadata."""
        observed_ranks = sorted({item.rank for report in history.reports for item in report.items})
        cutoffs = tuple(
            self._cutoff_effectiveness(history, rank, tuple(observed_ranks[:index]))
            for index, rank in enumerate(observed_ranks, start=1)
        )
        return SelectionResearchRankCutoffEffectivenessReport(
            evaluated_at=history.evaluated_at,
            start_date=history.start_date,
            end_date=history.end_date,
            snapshot_count=len(history.reports),
            empty_snapshot_count=sum(not report.items for report in history.reports),
            item_observation_count=sum(len(report.items) for report in history.reports),
            cutoffs=cutoffs,
        )

    def _cutoff_effectiveness(
        self,
        history: SelectionResearchReturnHistory,
        cutoff_rank: int,
        included_ranks: tuple[int, ...],
    ) -> SelectionResearchRankCutoffEffectiveness:
        filtered_history = _filtered_history(history, cutoff_rank)
        effectiveness = self._effectiveness_analyzer.analyze(filtered_history)
        return SelectionResearchRankCutoffEffectiveness(
            cutoff_rank=cutoff_rank,
            included_ranks=included_ranks,
            observation_count=effectiveness.item_observation_count,
            horizons=effectiveness.horizons,
        )


def _filtered_history(
    history: SelectionResearchReturnHistory, cutoff_rank: int
) -> SelectionResearchReturnHistory:
    """Retain every snapshot and original item order through one observed cutoff."""
    return SelectionResearchReturnHistory(
        evaluated_at=history.evaluated_at,
        start_date=history.start_date,
        end_date=history.end_date,
        reports=tuple(
            SelectionResearchReturnReport(
                snapshot_as_of=report.snapshot_as_of,
                evaluated_at=report.evaluated_at,
                anchor_date=report.anchor_date,
                items=tuple(item for item in report.items if item.rank <= cutoff_rank),
            )
            for report in history.reports
        ),
    )
