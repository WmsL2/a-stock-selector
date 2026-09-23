"""Pure filtering and in-memory export for persisted selection research snapshots."""

import csv
import json
from datetime import date, datetime
from io import StringIO

from pydantic import field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime

from .research import SelectionResearchItem, SelectionResearchSnapshot


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


class SelectionResearchItemObservation(DomainModel):
    snapshot_as_of: datetime
    strategy_name: str
    refresh_had_collection_failures: bool
    item: SelectionResearchItem

    @field_validator("snapshot_as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "snapshot_as_of")

    @model_validator(mode="after")
    def item_matches_snapshot(self) -> "SelectionResearchItemObservation":
        if self.item.as_of != self.snapshot_as_of:
            raise ValueError("research observation item as_of must match snapshot")
        return self


class SelectionResearchItemQueryReport(DomainModel):
    schema_version: int = 1
    start_date: date | None
    end_date: date | None
    strategy_name: str | None
    q: str | None
    board: str | None
    industry_code: str | None
    max_rank: int | None
    snapshot_count: int
    matching_snapshot_count: int
    item_observation_count: int
    observations: tuple[SelectionResearchItemObservation, ...]

    @model_validator(mode="after")
    def valid_report(self) -> "SelectionResearchItemQueryReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research query schema version")
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("start_date must not follow end_date")
        if self.max_rank is not None and self.max_rank <= 0:
            raise ValueError("max_rank must be positive")
        if not 0 <= self.matching_snapshot_count <= self.snapshot_count:
            raise ValueError("matching snapshot count must be within snapshot count")
        if self.item_observation_count != len(self.observations):
            raise ValueError("item observation count must match observations")
        return self


class SelectionResearchItemQueryAnalyzer:
    """Filter canonical snapshots without changing their supplied order."""

    def analyze(
        self,
        snapshots: tuple[SelectionResearchSnapshot, ...],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        strategy_name: str | None = None,
        q: str | None = None,
        board: str | None = None,
        industry_code: str | None = None,
        max_rank: int | None = None,
    ) -> SelectionResearchItemQueryReport:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start_date must not follow end_date")
        if max_rank is not None and max_rank <= 0:
            raise ValueError("max_rank must be positive")
        previous_as_of: datetime | None = None
        for snapshot in snapshots:
            if previous_as_of is not None and snapshot.as_of <= previous_as_of:
                raise ValueError("research snapshots must be strictly chronological")
            previous_as_of = snapshot.as_of

        normalized_strategy = _normalized_text(strategy_name)
        normalized_q = _normalized_text(q)
        normalized_board = _normalized_text(board)
        normalized_industry = _normalized_text(industry_code)
        observations: list[SelectionResearchItemObservation] = []
        snapshot_count = 0
        matching_snapshot_count = 0
        for snapshot in snapshots:
            if (
                (start_date is not None and snapshot.as_of.date() < start_date)
                or (end_date is not None and snapshot.as_of.date() > end_date)
                or (normalized_strategy is not None and snapshot.strategy_name != normalized_strategy)
            ):
                continue
            snapshot_count += 1
            matched_snapshot = False
            for item in snapshot.items:
                if not self._matches(
                    item,
                    q=normalized_q,
                    board=normalized_board,
                    industry_code=normalized_industry,
                    max_rank=max_rank,
                ):
                    continue
                observations.append(SelectionResearchItemObservation(
                    snapshot_as_of=snapshot.as_of,
                    strategy_name=snapshot.strategy_name,
                    refresh_had_collection_failures=snapshot.refresh_had_collection_failures,
                    item=item,
                ))
                matched_snapshot = True
            if matched_snapshot:
                matching_snapshot_count += 1
        return SelectionResearchItemQueryReport(
            start_date=start_date,
            end_date=end_date,
            strategy_name=normalized_strategy,
            q=normalized_q,
            board=normalized_board,
            industry_code=normalized_industry,
            max_rank=max_rank,
            snapshot_count=snapshot_count,
            matching_snapshot_count=matching_snapshot_count,
            item_observation_count=len(observations),
            observations=tuple(observations),
        )

    @staticmethod
    def _matches(
        item: SelectionResearchItem,
        *,
        q: str | None,
        board: str | None,
        industry_code: str | None,
        max_rank: int | None,
    ) -> bool:
        query = q.casefold() if q is not None else None
        return (
            (query is None or query in item.symbol.casefold() or query in item.name.casefold())
            and (board is None or item.board == board)
            and (industry_code is None or item.industry_code == industry_code)
            and (max_rank is None or item.rank <= max_rank)
        )


_CSV_COLUMNS = (
    "snapshot_as_of", "strategy_name", "refresh_had_collection_failures", "rank", "symbol",
    "name", "board", "industry_code", "industry_name", "base_score",
    "confidence_adjusted_score", "data_completeness", "confidence", "quality_score",
    "value_score", "growth_score", "momentum_score", "low_volatility_score",
    "evidence_json", "risks_json",
)


def selection_research_item_query_json(report: SelectionResearchItemQueryReport) -> str:
    """Serialize the exact report without touching the filesystem."""
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def selection_research_item_query_csv(report: SelectionResearchItemQueryReport) -> str:
    """Flatten matching observations in canonical order without creating a file."""
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for observation in report.observations:
        item = observation.item.model_dump(mode="json")
        writer.writerow({
            "snapshot_as_of": observation.snapshot_as_of.isoformat(),
            "strategy_name": observation.strategy_name,
            "refresh_had_collection_failures": observation.refresh_had_collection_failures,
            **{key: item[key] for key in _CSV_COLUMNS if key in item},
            "evidence_json": json.dumps(item["evidence"], ensure_ascii=False, separators=(",", ":")),
            "risks_json": json.dumps(item["risks"], ensure_ascii=False, separators=(",", ":")),
        })
    return output.getvalue()
