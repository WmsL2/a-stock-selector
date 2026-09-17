"""Durable, read-only research projections of official daily selections."""

import csv
import json
from datetime import datetime
from pathlib import Path

from pydantic import field_validator, model_validator

from stock_selector.config import AppPaths, Settings
from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.models.selection import Evidence, RiskFlag
from stock_selector.storage import LocalMarketRepository

from .models import DailySelectionDiagnostics, DailySelectionResult, SelectionBlocker


class SelectionResearchError(Exception):
    """Raised when a durable selection research artifact is invalid or unavailable."""


class SelectionResearchItem(DomainModel):
    rank: int
    as_of: datetime
    symbol: str
    name: str
    board: str
    industry_code: str | None
    industry_name: str | None
    base_score: float
    confidence_adjusted_score: float | None
    data_completeness: float
    confidence: float
    quality_score: float | None
    value_score: float | None
    growth_score: float | None
    momentum_score: float | None
    low_volatility_score: float | None
    evidence: tuple[Evidence, ...]
    risks: tuple[RiskFlag, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def valid_rank(self) -> "SelectionResearchItem":
        if self.rank <= 0:
            raise ValueError("research item rank must be positive")
        return self


class SelectionResearchSnapshot(DomainModel):
    schema_version: int = 1
    as_of: datetime
    strategy_name: str
    selection_ready: bool
    blockers: tuple[SelectionBlocker, ...]
    refresh_had_collection_failures: bool
    diagnostics: DailySelectionDiagnostics
    items: tuple[SelectionResearchItem, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def exact_snapshot(self) -> "SelectionResearchSnapshot":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research schema version")
        if self.diagnostics.as_of != self.as_of:
            raise ValueError("research diagnostics must match snapshot as_of")
        if self.selection_ready != self.diagnostics.selection_ready:
            raise ValueError("research readiness must match diagnostics")
        if self.blockers != self.diagnostics.blockers:
            raise ValueError("research blockers must match diagnostics")
        if len(self.items) != self.diagnostics.returned_items or self.selection_ready != bool(self.items):
            raise ValueError("research items must match official readiness and returned count")
        if len({item.symbol for item in self.items}) != len(self.items):
            raise ValueError("research item symbols must be unique")
        if len({item.rank for item in self.items}) != len(self.items):
            raise ValueError("research item ranks must be unique")
        if any(item.as_of != self.as_of for item in self.items):
            raise ValueError("research item as_of must match snapshot")
        return self


class SelectionResearchExportResult(DomainModel):
    snapshot: SelectionResearchSnapshot
    json_path: str
    csv_path: str


class SelectionResearchSnapshotBuilder:
    """Project an already-authoritative selection without recomputation or ordering changes."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def build(self, result: DailySelectionResult, *, refresh_had_collection_failures: bool) -> SelectionResearchSnapshot:
        instruments = {item.symbol: item for item in self._repository.load_instruments()}
        items: list[SelectionResearchItem] = []
        for score in result.selection.items:
            if score.market_rank is None:
                raise SelectionResearchError("official selection item market_rank is required for export")
            instrument = instruments.get(score.symbol)
            if instrument is None:
                raise SelectionResearchError("official selection item is missing from instrument master")
            industries = tuple(
                item for item in self._repository.load_industry_records(score.symbol, as_of=result.as_of.date())
                if item.classification == self._settings.selection.industry_classification
            )
            if len(industries) > 1:
                raise SelectionResearchError("multiple active records for selected classification")
            industry = industries[0] if industries else None
            items.append(SelectionResearchItem(
                rank=score.market_rank, as_of=score.as_of, symbol=score.symbol,
                name=instrument.name, board=instrument.board.value,
                industry_code=industry.industry_code if industry else None,
                industry_name=industry.industry_name if industry else None,
                base_score=score.base_score,
                confidence_adjusted_score=score.confidence_adjusted_score,
                data_completeness=score.data_completeness, confidence=score.confidence,
                quality_score=score.quality_score, value_score=score.value_score,
                growth_score=score.growth_score, momentum_score=score.momentum_score,
                low_volatility_score=score.low_volatility_score,
                evidence=score.evidence, risks=score.risks,
            ))
        return SelectionResearchSnapshot(
            as_of=result.as_of, strategy_name=result.selection.strategy_name,
            selection_ready=result.diagnostics.selection_ready,
            blockers=result.diagnostics.blockers,
            refresh_had_collection_failures=refresh_had_collection_failures,
            diagnostics=result.diagnostics, items=tuple(items),
        )


class SelectionResearchArtifactStore:
    """Write JSON-last date-scoped artifacts and load their canonical JSON snapshots."""

    _csv_columns = (
        "rank", "symbol", "name", "board", "industry_code", "industry_name", "base_score",
        "confidence_adjusted_score", "data_completeness", "confidence", "quality_score",
        "value_score", "growth_score", "momentum_score", "low_volatility_score",
        "evidence_json", "risks_json",
    )

    def __init__(self, paths: AppPaths) -> None:
        self._root = paths.snapshots_dir / "selection"

    def export(self, snapshot: SelectionResearchSnapshot) -> SelectionResearchExportResult:
        directory = self._root / snapshot.as_of.date().isoformat()
        directory.mkdir(parents=True, exist_ok=True)
        json_path, csv_path = directory / "selection.json", directory / "selection.csv"
        json_temp, csv_temp = directory / ".selection.json.tmp", directory / ".selection.csv.tmp"
        csv_backup = directory / ".selection.csv.bak"
        csv_backed_up = False
        csv_promoted = False
        committed = False
        try:
            self._write_csv(csv_temp, snapshot)
            json_temp.write_text(self.canonical_json(snapshot), encoding="utf-8", newline="\n")
            if csv_path.exists():
                csv_path.replace(csv_backup)
                csv_backed_up = True
            csv_temp.replace(csv_path)
            csv_promoted = True
            json_temp.replace(json_path)
            committed = True
        except OSError as exc:
            if csv_backed_up:
                try:
                    csv_backup.replace(csv_path)
                except OSError:
                    pass
            elif csv_promoted:
                try:
                    csv_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise SelectionResearchError("could not export selection research artifact") from exc
        finally:
            for temporary in (json_temp, csv_temp):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            if committed:
                try:
                    csv_backup.unlink(missing_ok=True)
                except OSError:
                    pass
        return SelectionResearchExportResult(
            snapshot=snapshot, json_path=str(json_path), csv_path=str(csv_path)
        )

    def load_latest(self) -> SelectionResearchSnapshot | None:
        if not self._root.exists():
            return None
        snapshots: list[SelectionResearchSnapshot] = []
        for json_path in self._root.glob("*/selection.json"):
            try:
                snapshots.append(SelectionResearchSnapshot.model_validate_json(json_path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                raise SelectionResearchError("corrupt selection research artifact") from exc
        return max(snapshots, key=lambda item: item.as_of) if snapshots else None

    def latest_json_path(self) -> Path | None:
        snapshot = self.load_latest()
        return self._path_for(snapshot, "selection.json") if snapshot else None

    def latest_csv_path(self) -> Path | None:
        snapshot = self.load_latest()
        if snapshot is None:
            return None
        path = self._path_for(snapshot, "selection.csv")
        if not path.is_file():
            raise SelectionResearchError("committed selection CSV is missing")
        return path

    def canonical_json(self, snapshot: SelectionResearchSnapshot) -> str:
        return json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    def _path_for(self, snapshot: SelectionResearchSnapshot, filename: str) -> Path:
        return self._root / snapshot.as_of.date().isoformat() / filename

    def _write_csv(self, path: Path, snapshot: SelectionResearchSnapshot) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._csv_columns)
            writer.writeheader()
            for item in snapshot.items:
                row = item.model_dump(mode="json")
                writer.writerow({
                    key: row[key] for key in self._csv_columns if key not in {"evidence_json", "risks_json"}
                } | {
                    "evidence_json": json.dumps(row["evidence"], ensure_ascii=False, separators=(",", ":")),
                    "risks_json": json.dumps(row["risks"], ensure_ascii=False, separators=(",", ":")),
                })
