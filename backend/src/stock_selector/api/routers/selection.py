"""Read-only on-demand daily BaseScore selection route."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from stock_selector.api.dependencies import (
    aware_timestamp,
    get_realtime_provider,
    get_repository,
    get_settings,
)
from stock_selector.api.realtime_selection import RealtimeSelectionAPIService
from stock_selector.api.schemas import (
    DailySelectionDiagnosticsResponse,
    DailySelectionResponse,
    EvidenceResponse,
    RealtimeSelectionResponse,
    RiskFlagResponse,
    SelectionResearchEffectivenessResponse,
    SelectionResearchHorizonEffectivenessResponse,
    SelectionResearchItemResponse,
    SelectionResearchLatestResponse,
    SelectionResearchRankCutoffEffectivenessResponse,
    SelectionResearchRankEffectivenessResponse,
    SelectionResearchSnapshotResponse,
)
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.config import Settings
from stock_selector.models.common import ensure_aware_datetime
from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.selection import (
    SelectionResearchArtifactStore,
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchError,
    SelectionResearchHorizonEffectiveness,
    SelectionResearchRankCutoffEffectivenessAnalyzer,
    SelectionResearchRankEffectivenessAnalyzer,
    SelectionResearchReturnHistoryBuilder,
    SelectionResearchReturnLabeler,
)
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/selection", tags=["selection"])


def _horizon_effectiveness_response(
    horizon: SelectionResearchHorizonEffectiveness,
) -> SelectionResearchHorizonEffectivenessResponse:
    return SelectionResearchHorizonEffectivenessResponse(**horizon.model_dump())


def _research_effectiveness_response(
    repository: LocalMarketRepository,
    evaluated_at: datetime,
    start_date: date | None,
    end_date: date | None,
) -> SelectionResearchEffectivenessResponse:
    try:
        store = SelectionResearchArtifactStore(repository.paths)
        labeler = SelectionResearchReturnLabeler(repository)
        history = SelectionResearchReturnHistoryBuilder(store, labeler).build(
            evaluated_at,
            start_date=start_date,
            end_date=end_date,
        )
    except SelectionResearchError as exc:
        raise HTTPException(
            status_code=503,
            detail="selection research artifact unavailable",
        ) from exc
    overall = SelectionResearchEffectivenessAnalyzer().analyze(history)
    ranks = SelectionResearchRankEffectivenessAnalyzer().analyze(history)
    cutoffs = SelectionResearchRankCutoffEffectivenessAnalyzer().analyze(history)
    return SelectionResearchEffectivenessResponse(
        evaluated_at=overall.evaluated_at,
        start_date=overall.start_date,
        end_date=overall.end_date,
        snapshot_count=overall.snapshot_count,
        empty_snapshot_count=overall.empty_snapshot_count,
        item_observation_count=overall.item_observation_count,
        overall_horizons=[
            _horizon_effectiveness_response(horizon)
            for horizon in overall.horizons
        ],
        ranks=[
            SelectionResearchRankEffectivenessResponse(
                rank=rank.rank,
                observation_count=rank.observation_count,
                horizons=[
                    _horizon_effectiveness_response(horizon)
                    for horizon in rank.horizons
                ],
            )
            for rank in ranks.ranks
        ],
        cutoffs=[
            SelectionResearchRankCutoffEffectivenessResponse(
                cutoff_rank=cutoff.cutoff_rank,
                included_ranks=list(cutoff.included_ranks),
                observation_count=cutoff.observation_count,
                horizons=[
                    _horizon_effectiveness_response(horizon)
                    for horizon in cutoff.horizons
                ],
            )
            for cutoff in cutoffs.cutoffs
        ],
    )


def _research_response(repository: LocalMarketRepository) -> SelectionResearchLatestResponse:
    try:
        snapshot = SelectionResearchArtifactStore(repository.paths).load_latest()
    except SelectionResearchError as exc:
        raise HTTPException(status_code=503, detail="selection research artifact unavailable") from exc
    if snapshot is None:
        return SelectionResearchLatestResponse(available=False, snapshot=None)
    diagnostics = snapshot.diagnostics
    return SelectionResearchLatestResponse(available=True, snapshot=SelectionResearchSnapshotResponse(
        schema_version=snapshot.schema_version, as_of=snapshot.as_of,
        strategy_name=snapshot.strategy_name, selection_ready=snapshot.selection_ready,
        blockers=[item.value for item in snapshot.blockers],
        refresh_had_collection_failures=snapshot.refresh_had_collection_failures,
        diagnostics=DailySelectionDiagnosticsResponse(**diagnostics.model_dump(exclude={"as_of", "selection_ready", "blockers"})),
        items=[SelectionResearchItemResponse(
            **item.model_dump(exclude={"evidence", "risks"}),
            evidence=[EvidenceResponse(**value.model_dump()) for value in item.evidence],
            risks=[RiskFlagResponse(code=value.code, message=value.message, severity=value.severity.value) for value in item.risks],
        ) for item in snapshot.items],
    ))


@router.get("/research/latest", response_model=SelectionResearchLatestResponse)
def get_selection_research_latest(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> SelectionResearchLatestResponse:
    return _research_response(repository)


@router.get("/research/effectiveness", response_model=SelectionResearchEffectivenessResponse)
def get_selection_research_effectiveness(
    evaluated_at: Annotated[datetime, Query()],
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> SelectionResearchEffectivenessResponse:
    """Project one explicit-time read-only research-label history into summaries."""
    try:
        resolved_evaluated_at = ensure_aware_datetime(evaluated_at, "evaluated_at")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not follow end_date")
    return _research_effectiveness_response(
        repository,
        resolved_evaluated_at,
        start_date,
        end_date,
    )


@router.get("/research/latest.json")
def download_selection_research_json(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> FileResponse:
    try:
        store = SelectionResearchArtifactStore(repository.paths)
        snapshot = store.load_latest()
        path = store.latest_json_path() if snapshot else None
    except SelectionResearchError as exc:
        raise HTTPException(status_code=503, detail="selection research artifact unavailable") from exc
    if snapshot is None or path is None:
        raise HTTPException(status_code=404, detail="selection research artifact not found")
    return FileResponse(path, media_type="application/json", filename=f"selection-{snapshot.as_of.date().isoformat()}.json")


@router.get("/research/latest.csv")
def download_selection_research_csv(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> FileResponse:
    try:
        store = SelectionResearchArtifactStore(repository.paths)
        snapshot = store.load_latest()
        path = store.latest_csv_path() if snapshot else None
    except SelectionResearchError as exc:
        raise HTTPException(status_code=503, detail="selection research artifact unavailable") from exc
    if snapshot is None or path is None:
        raise HTTPException(status_code=404, detail="selection research artifact not found")
    return FileResponse(path, media_type="text/csv", filename=f"selection-{snapshot.as_of.date().isoformat()}.csv")


@router.get("/daily", response_model=DailySelectionResponse)
def get_daily_selection(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    as_of: Annotated[datetime | None, Query()] = None,
) -> DailySelectionResponse:
    """Return truthful local selection readiness or an on-demand ranked result."""
    resolved_as_of = aware_timestamp(as_of) or datetime.now(
        ZoneInfo(settings.app.timezone)
    )
    return ReadOnlyMarketService(repository).daily_selection(settings, resolved_as_of)


@router.get("/realtime", response_model=RealtimeSelectionResponse)
def get_realtime_selection(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[RealtimeMarketDataProvider, Depends(get_realtime_provider)],
    as_of: Annotated[datetime | None, Query()] = None,
) -> RealtimeSelectionResponse:
    """Project one all-market Task25 runtime execution into the compact Top100 API DTO."""
    resolved_as_of = aware_timestamp(as_of) or datetime.now(
        ZoneInfo(settings.app.timezone)
    )
    return RealtimeSelectionAPIService(repository, settings, provider).build(
        resolved_as_of
    )
