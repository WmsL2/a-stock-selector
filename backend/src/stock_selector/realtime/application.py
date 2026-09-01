"""Pure Task23 application orchestration over supplied Task15-to-Task22 inputs."""

from datetime import datetime

from stock_selector.risk import RiskEligibilitySnapshot
from stock_selector.scoring import BaseScoreCrossSectionResult

from .candidate_snapshot import RealtimeCandidateSnapshotEngine
from .candidates import RealtimeCandidateEngine
from .intraday_factors import RealtimeIntradayFactorEngine
from .intraday_score import RealtimeIntradayScoreEngine
from .light_scanner import RealtimeLightScannerEngine
from .models import (
    RealtimeCaptureResult,
    RealtimeSelectionPipelinePolicy,
    RealtimeSelectionPipelineResult,
)
from .realtime_score import RealtimeScoreEngine
from .realtime_selection import RealtimeSelectionEngine
from .signal_normalizer import RealtimeSignalNormalizerEngine


class RealtimeSelectionApplicationService:
    """Run the existing pure Task15-to-Task22 engines exactly once in canonical order."""

    def run(
        self,
        base_scores: BaseScoreCrossSectionResult,
        risk: RiskEligibilitySnapshot,
        capture: RealtimeCaptureResult | None,
        calculation_at: datetime,
        policy: RealtimeSelectionPipelinePolicy | None = None,
    ) -> RealtimeSelectionPipelineResult:
        resolved = policy or RealtimeSelectionPipelinePolicy()
        candidates = RealtimeCandidateEngine().build(base_scores, risk, resolved.candidate_policy)
        snapshot = RealtimeCandidateSnapshotEngine().build(
            candidates,
            capture,
            calculation_at,
            resolved.freshness_normal_max_seconds,
            resolved.freshness_warning_max_seconds,
        )
        scan = RealtimeLightScannerEngine().scan(snapshot, resolved.light_scan_policy)
        normalization = RealtimeSignalNormalizerEngine().normalize(scan)
        factors = RealtimeIntradayFactorEngine().compute(normalization)
        intraday_score = RealtimeIntradayScoreEngine().compute(
            factors, resolved.intraday_score_policy
        )
        realtime_score = RealtimeScoreEngine().compute(
            intraday_score, resolved.realtime_score_policy
        )
        selection = RealtimeSelectionEngine().select(
            realtime_score, resolved.selection_policy
        )
        return RealtimeSelectionPipelineResult(
            calculation_at=calculation_at,
            candidate_as_of=candidates.as_of,
            policy=resolved,
            candidates=candidates,
            snapshot=snapshot,
            scan=scan,
            normalization=normalization,
            factors=factors,
            intraday_score=intraday_score,
            realtime_score=realtime_score,
            selection=selection,
        )
