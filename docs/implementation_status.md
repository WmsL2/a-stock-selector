# Implementation Status

## Current Task

Task 17 - Realtime Light Scanner Foundation

## Status

Completed

## Completed

- Python 3.12 project scaffold
- src layout
- package initialization
- CLI entry point
- pytest configuration
- Ruff configuration
- mypy configuration
- README
- .gitignore
- README correctly tracked
- generated egg-info excluded
- repository scaffold repaired
- Pydantic configuration models
- YAML configuration loader
- recursive config merge
- application paths
- logging infrastructure
- configuration CLI
- configuration tests
- logging tests
- hardened configuration error handling
- canonical security identifiers
- instrument domain model
- market data models
- financial data models
- industry history model
- factor data models
- selection and explanation models
- timezone-aware validation
- finite-number validation
- provider capability interfaces
- typed provider request models
- provider error hierarchy
- offline provider contract tests
- provider/domain separation
- AKShare provider
- exchange instrument mapping
- canonical AKShare symbol mapping
- realtime snapshot mapping
- Eastmoney realtime primary with Sina connection-failure fallback
- daily bar mapping
- lot-to-share volume normalization
- provider error translation
- explicit DailyBar adjustment basis
- Eastmoney daily primary with Sina connection-failure fallback
- RAW-only AKShare daily capability
- lightweight tiered storage architecture
- explicit PyArrow schemas
- selective per-symbol daily persistence
- selective realtime snapshot persistence
- atomic Parquet writes
- DuckDB external views
- storage coverage statistics
- disk usage reporting
- AKShare-to-storage selective live smoke
- FastAPI application factory
- local repository dependency injection
- health endpoint
- storage status API
- instrument listing/detail APIs
- daily local-data API
- realtime local-data API
- public safe-config API
- explicit response DTO contracts
- read-only HTTP boundary
- API/storage/provider separation
- OpenAPI development docs
- Vue 3 application shell
- TypeScript frontend
- Vite development server
- Vue Router navigation
- Pinia application state
- Element Plus research-terminal layout
- FastAPI Axios client
- storage dashboard
- instrument browser
- local stock detail page
- ECharts local OHLC chart
- safe public settings page
- truthful unimplemented states
- Vite-to-FastAPI proxy integration
- truthful API status initialization
- route-aware navigation state
- independent stock-detail error states
- point-in-time structural A-share universe
- deterministic board inclusion
- listing/delisting lifecycle filtering
- zero-day default new-listing policy
- auditable structural exclusion reasons
- survivorship-bias safety disclosure
- universe status API
- offline universe CLI
- Vue structural universe status integration
- dated tri-state risk records
- exact-date risk eligibility evaluation
- missing-risk conservative semantics
- risk-state Parquet persistence
- DuckDB risk-state view
- risk coverage quality reporting
- configurable realtime freshness thresholds
- realtime freshness evaluation
- quality status API and CLI
- Vue quality and risk coverage status
- app-scoped API settings dependency
- bounded daily-price collection pipeline
- provider-abstraction collector
- per-symbol failure isolation
- provider-result boundary validation
- selective RAW daily persistence
- idempotent daily upsert workflow
- daily storage range statistics
- read-only daily status API
- daily CLI collection and status
- Vue daily-storage status integration
- explicit RAW and corporate-action semantics
- backend/src and backend/tests monorepo relocation
- backend-local Python packaging and tool caches
- workspace-root AppPaths with backend config and runtime state roots
- preserved local Parquet, DuckDB, log and snapshot runtime migration
- root PowerShell start and complete-validation scripts
- repository-layout architecture documentation
- immutable raw/preprocessed factor observations
- explicit missing-value policies
- market-median imputation
- industry-median imputation
- scaled-MAD winsorization
- percentile normalization
- higher/lower-is-better direction
- optional industry percentile neutralization
- transparent imputation/winsorization metadata
- deterministic cross-sectional processing
- preprocessing diagnostics
- pure offline preprocessing architecture
- Quality factor family
- Value factor family
- Growth factor family
- Momentum factor family
- Low Volatility factor family
- positive-multiple valuation semantics
- conservative YoY base policy
- adjusted-price-only momentum/volatility contract
- Task10 preprocessing integration
- family component coverage
- deterministic family aggregation
- point-in-time factor-input validation
- configurable five-family BaseScore
- available-family weight renormalization
- missing-family-is-not-zero semantics
- family-level data completeness
- component-coverage-weighted confidence
- confidence-adjusted score
- auditable configured/renormalized weights
- family contribution breakdown
- no-factor unavailable score semantics
- deterministic pure scoring engine
- local PIT daily selection orchestration
- structural universe integration
- conservative exact-date risk gating
- point-in-time financial input assembly
- point-in-time valuation input assembly
- explicit PIT industry classification
- FiveFactorEngine integration
- BaseScoreEngine integration
- deterministic BaseScore ranking
- TopN selection
- read-only daily selection API
- truthful readiness diagnostics
- Vue daily selection page
- missing-family display semantics
- current local risk-not-ready handling
- BaseScore descending ranking regression coverage
- deterministic symbol tie-break and market-rank coverage
- service-side TopN truncation and no-score exclusion coverage
- low-completeness rankability coverage without a threshold
- ready and not-ready selection API contract coverage
- Vue ready, not-ready, loading, error and instrument-navigation coverage
- deterministic structured evidence engine
- BaseScore contribution evidence
- strongest/weakest component evidence
- missing-family limitation flags
- partial-family coverage flags
- completeness/confidence severity flags
- operational price-factor limitation
- stable evidence/risk ordering
- Daily Selection explanation integration
- read-only API explanation fields
- Vue expandable explanation display
- no-LLM evidence boundary
- explanation-does-not-change-ranking regression

## Task 12A Verification

- `python -m pip install -e ".\\backend[dev]"` — PASS; the editable package remains
  `stock_selector` from `backend/src`.
- `python -m stock_selector config paths` — PASS from the workspace root; configuration
  resolves under `backend/config`, while data, logs and snapshots resolve under `runtime/`.
- `python -m stock_selector storage status` — PASS offline after the migration: 5,551
  instruments, 5 daily rows, 3 realtime rows and 909.4 KB retained.
- `scripts/test-all.ps1` — PASS: 405 backend tests, 88% coverage, Ruff, mypy,
  frontend type check, lint, 34 Vitest tests and production build all completed.
- Task 12A Fix regressions — PASS offline: BaseScore-descending ranking, symbol-ascending
  ties, market ranks, service-side TopN, no-score exclusion and low-completeness ranking are
  verified with synthetic temporary repositories; confidence-adjusted score does not rank.
- Task 12A Fix API/UI contracts — PASS: synthetic ready API returns Q/V/G-only ranked items
  with 0.75 completeness and null Momentum/LowVol; not-ready risk coverage, Vue ready,
  not-ready, loading, HTTP-error and instrument-navigation states are covered.
- Task 12A Fix runtime smoke — PASS read-only: `/api/selection/daily` returned HTTP 200 with
  5,551 structural members, zero complete risk records, `selection_ready=false` and no items;
  no runtime risk, factor or market data was written.
- Backend script smoke — PASS: localhost `/api/health`, `/api/storage/status` and `/docs`
  returned 200.
- Frontend script and Vite proxy smoke — PASS: localhost `/`, `/api/health` and
  `/api/storage/status` returned 200. Temporary local processes were stopped afterwards.

## Task 13 Verification

- `tests/explanation` — PASS (16 tests): contribution points, strongest/weakest components,
  missing/partial families, thresholds, RAW-price limitation, identity, determinism and purity.
- Daily Selection and API integration — PASS: ready items contain ordered structured evidence and
  limitations, while incomplete risk coverage still returns no items or explanation objects.
- Vue Daily Selection — PASS: expandable evidence/limitation display, severity mapping, no-risk
  disclaimer and investment-advice disclaimer are covered without changing the ranking table.

## Tests

The canonical full validation entry point is `./scripts/test-all.ps1`.

- `./.venv/Scripts/python.exe -m pip install -e ".\\backend[dev]"` — PASS
- Backend validation (from `backend/`): `..\\.venv\\Scripts\\python.exe -m pytest` — PASS
  (405 passed; one third-party TestClient deprecation warning).
- Backend coverage (from `backend/`):
  `..\\.venv\\Scripts\\python.exe -m pytest --cov=stock_selector --cov-report=term-missing`
  — PASS (405 passed, 88% coverage).
- Backend static checks (from `backend/`): `..\\.venv\\Scripts\\ruff.exe check .` and
  `..\\.venv\\Scripts\\mypy.exe src` — PASS.
- Frontend validation (from `frontend/`): `npm install`, `npm run type-check`, `npm run lint`,
  `npm run test` — PASS (34 passed), and `npm run build` — PASS.
- `git diff --check` — PASS.

## Live Smoke

- `storage smoke 600519.SH --start 2026-08-03 --end 2026-08-07` — PASS.
  Eastmoney daily and realtime calls both failed at their connection boundaries,
  then completed through Sina: daily source `akshare:stock_zh_a_daily`,
  adjustment `raw`; realtime source `akshare:stock_zh_a_spot`.
  The successful snapshot round-trip saved Instrument universe 5,551,
  Daily `600519.SH` 5 rows, and one selected realtime quote.
- `storage status` — PASS offline: Instrument universe 5,551; Daily stored
  symbols 1 / rows 5; Realtime stored symbols 1 / snapshots 3 / rows 3;
  latest realtime 2026-08-28T17:26:59.333499+08:00; disk usage 909.4 KB.
  The additional snapshots are prior bounded retry attempts for the same
  single symbol, not all-market realtime persistence.
- FastAPI Uvicorn/API smoke — PASS on `127.0.0.1:8000`: `/api/health`,
  `/api/storage/status`, `/api/instruments/600519.SH`, and `/docs` returned 200.
  The server was stopped after the local smoke check.
- Vue/FastAPI integration — PASS on localhost: Vite `/` returned 200; Vite proxy
  requests to `/api/health` and `/api/storage/status` returned 200. Both local
  development processes were stopped after verification.
- Universe API/CLI/Vue integration — PASS: local CLI reported 5,551 input and
  5,551 structural members on 2026-08-29; FastAPI `/api/universe/status` and
  the Vite proxy both returned 200. The local processes were stopped after smoke.
- Quality API/CLI/Vue integration — PASS: local risk-state storage remains intentionally
  empty (0 rows / 0 dates); `/api/quality/status` and the Vite proxy returned 200 with
  `risk_filter_ready=false`, `risk_eligible_instruments=null`, and stale local realtime
  freshness. Both local processes were stopped after smoke.
- Daily collection/API/Vue integration — PASS: two identical explicit RAW collections for
  `600519.SH` from 2026-08-03 through 2026-08-07 each returned 5 rows through the Sina
  fallback (`akshare:stock_zh_a_daily`); local storage remained 1 symbol / 5 rows with no
  duplicate dates. FastAPI and Vite `/api/daily/status` both returned 200, then stopped.
- Fundamentals / valuation / industry foundation — complete: explicit-symbol collectors,
  typed Parquet schemas and DuckDB views, read-only APIs and CLI status are implemented.
  Financial records use the source announcement date plus conservative 15:30 Asia/Shanghai
  availability; revisions are retained rather than overwritten. Valuation history currently
  covers dated PE (TTM), PB, PCF and total market cap only (CNY-normalized); negative PE and
  unavailable metrics are retained faithfully. CNInfo industry change events form intervals
  within each classification; no pre-first-event history is fabricated.
- Task 09 bounded live collection/API/Vue integration — PASS for `600519.SH` only:
  the financial collector persisted 6 announcement-dated records, the valuation collector
  persisted 1,218 dated observations, and the industry collector persisted 10 CNInfo
  intervals. A direct temporary Uvicorn instance on port 8001 returned those counts from
  `/api/fundamentals/status`; the per-instrument fundamentals, valuation and industry
  endpoints returned 200 during the local integration check. The temporary process was
  stopped afterwards.
- Task 09 financial mapping fix — PASS for an explicit bounded `600519.SH` refresh from
  2025-01-01 through 2026-12-31: 6 logical financial rows remained idempotent. For report
  period 2025-12-31 (announcement 2026-04-17), source `ZZCJLL`, mapped ROA and persisted ROA
  were all `28.3056525971`; `TOTAL_ROI` was null and was not used as a fallback.
- Task 10 preprocessing — PASS entirely offline: generic raw observations are transformed
  through explicit missing-value policy, scaled-MAD winsorization and market or explicit
  industry percentile ranking. No market data, repository, provider, API, persistence or UI
  dependency is involved.
- Task 11 five-family computation — PASS offline with explicit point-in-time inputs only.
  Operational RAW daily data remains ineligible for Momentum and Low Volatility until an
  explicitly corporate-action-adjusted price series is supplied.
- Task 11 mathematical regression hardening — PASS: component-level synthetic formulas,
  full engine cross-sectional ranking, family renormalization, PIT rejection and deterministic
  result ordering are covered without runtime data or network access.
- Task 11 remaining PIT/model/window/low-volatility regression gaps — closed with synthetic
  engine, direct-formula and domain-contract coverage only.
- Task 12 BaseScore — PASS entirely offline: caller-supplied configured weights compose
  immutable five-factor cross sections with available-weight renormalization, family-level
  completeness, coverage-weighted confidence and contribution audit trails only.
- Task 12A daily selection — PASS with local-only structural universe, exact-date conservative
  risk coverage, PIT factor-input assembly, deterministic BaseScore ranking and a read-only API/UI.
- Task 12A Fix — PASS: regression coverage now proves BaseScore-first ranking, deterministic
  ties, TopN, no-score behavior, no completeness threshold, ready/not-ready API contracts and
  Vue rendering without writing runtime data or using a provider/network.
- Task 13 deterministic explanation — PASS: pure structured Evidence/RiskFlag output is derived
  only from factor, BaseScore and completeness inputs; it adds no persistence, provider, network,
  LLM or recommendation behavior and does not alter ranking or risk gating.

## Not Implemented Yet

- Full historical risk-state collector
- Full-market daily data quality
- Long-no-trade detection
- Full-market scheduled daily refresh
- Trading-calendar gap detection
- Corporate-action-adjusted return series
- Full historical research dataset
- Realtime cross-sectional scanner ranking / scoring
- Minute bars
- Intraday factors
- IntradayScore
- RealTimeScore
- Replay engine
- Backtest
- Factor research
- Scheduler

## Task 14 — Realtime Market Data Foundation (complete)

- `RealtimeSnapshotCollector` captures a provider batch exactly once. It distinguishes
  `None` all-market scope from an explicit canonical symbol tuple, rejects empty and
  duplicate batches, validates exact explicit request/response equality, and requires a
  single source plus a single aware `ingested_at` across a returned snapshot.
- Application-core full-market capture can persist only an explicitly named returned subset;
  it never persists an entire returned all-market batch. The CLI has no subset-selection flag
  for `--all-market`, so `realtime capture --all-market --persist` is rejected before provider
  construction. No scheduler, polling loop, or full-market runtime write was added.
- Source timestamps are not fabricated: current Eastmoney and Sina mappings retain
  `source_timestamp=None`; `ingested_at` is the provider-boundary collection instant.
- The repository-only status service evaluates configured 60/120-second freshness at a
  caller-supplied `calculation_at`. `fresh` and `warning` pass the freshness gate;
  `stale` and `unavailable` do not. Future ingestion is rejected.
- `GET /api/realtime/status`, CLI `realtime status`, and the realtime Vue view display only
  the locally persisted selective snapshot state. They do not collect data or claim that
  `Realtime Scanner`, `IntradayScore`, or `RealTimeScore` exists.

## Task 14 Verification

- `tests/realtime` plus `tests/api/test_realtime_status_api.py` — PASS (40 tests).
- Full backend validation — PASS (351 tests; 88% coverage); Ruff and mypy pass.
- Frontend type check, lint, Vitest (34 tests), and production build — PASS.
- Offline collector regressions cover all-market no-persist capture, an explicitly persisted
  all-market subset, exact explicit request matching, provider-error translation with preserved
  causes, programming-error propagation, and a 50-symbol single provider call.
- Offline status regressions cover source-timestamp availability and ingestion-based freshness:
  a one-day-old source timestamp with a 30-second local ingestion age remains fresh and allows
  ranking; 60/61/120/121-second and unavailable boundaries remain explicit.
- Offline CLI regressions prove that `realtime status` constructs no provider and formats in the
  configured `Asia/Shanghai` timezone; capture is one provider call, writes only when explicit
  symbols use `--persist`, and full-market persistence fails before runtime access.
- Realtime status API regressions expose freshness metadata and prove repository-only read-only
  behavior. The Vue realtime view was intentionally unchanged.
- One one-shot all-market realtime live smoke was performed: `AKShareProvider` encountered an
  Eastmoney realtime connection-boundary failure, then the Sina fallback returned 5,546 quotes
  from `akshare:stock_zh_a_spot` at `2026-08-30T16:09:49.472584+08:00`. Source timestamps were
  available for 0 quotes and 0 quotes were persisted, so the full-market result existed only in
  the capture result / memory; runtime realtime snapshots remained 3 and realtime rows remained
  3. This subsequent Task 14 Fix performed no additional live call or runtime write.

## Task 15 — Realtime Candidate Foundation (complete)

- `RealtimeCandidateEngine` is a pure, deterministic slow-layer reduction over a complete
  `BaseScoreCrossSectionResult` and an already-built exact-date `RiskEligibilitySnapshot`.
  It has no provider, repository, persistence, API, CLI, frontend, network, or wall-clock
  dependency.
- The immutable default policy requires both `base_score >= 70.0` and membership in the top
  `ceil(N * 0.20)` BaseScore ranks of the scoreable risk-eligible universe. Ranking is
  BaseScore descending then symbol ascending; confidence-adjusted score, completeness and
  confidence never affect membership or ordering.
- Candidate diagnostics record structural/risk/scoreable counts, the policy cutoff, top bucket,
  threshold-qualified members, final candidates and stable readiness blockers. Complete,
  scoreable inputs can truthfully yield a ready empty result when no member meets the policy.
- No realtime light scanner, realtime quote candidate integration, IntradayScore, RealTimeScore,
  Top100, Top20, scheduler, polling loop, API endpoint, CLI command, persistence, or Vue
  candidate table was added.

## Task 15 Verification

- `tests/realtime` — PASS (55 tests), including policy validation, BaseScore-only ranking,
  ceil top-fraction boundaries, threshold intersection, risk gating, structural-symbol integrity,
  ready-empty semantics, determinism and dependency boundaries.
- Full backend validation — PASS (369 tests); Ruff and mypy pass. The canonical root validation
  also covers backend coverage and the unchanged frontend checks.

## Task 16 — Realtime Candidate Snapshot Join (complete)

- `RealtimeCandidateSnapshotEngine` purely and deterministically joins an unchanged Task 15
  candidate result with an optional Task 14 capture at an explicit calculation timestamp. It
  preserves Task 15 candidate order and membership; quote fields remain observational only.
- Non-empty candidate pools require temporal causality (`candidate as_of <= capture ingested_at
  <= calculation_at`), existing ingestion-based freshness permission (fresh/warning only), and
  100% candidate quote coverage. Incomplete coverage or disallowed freshness returns no partial
  official items with stable diagnostics and blockers.
- A candidate pool that is not ready is blocked without a realtime fallback. A ready-empty pool
  is truthfully snapshot-ready without a capture. Both all-market and explicit capture scopes
  are supported when candidate symbols are fully covered.
- No realtime light scanner / engine, quote-derived ranking, Relative Strength, Activity /
  Liquidity, VWAP / Trend, Short Momentum, IntradayScore, RealTimeScore, Top100, Top20, minute
  bars, scheduler, polling loop, API, CLI, Vue candidate view, or candidate snapshot persistence
  was added.

## Task 16 Verification

- `tests/realtime` — PASS (74 tests), covering all-market and explicit joins, rank preservation,
  no quote-value filtering, ready/blocked/ready-empty semantics, coverage, freshness boundaries,
  temporal causality, source timestamp semantics, capture identity and dependency boundaries.
- Full backend validation — PASS (388 tests); Ruff and mypy pass. The canonical root validation
  also covers backend coverage and the unchanged frontend checks.

## Task 17 — Realtime Light Scanner Foundation (complete)

- `RealtimeLightScannerEngine` is a pure deterministic annotation layer that consumes only a
  validated Task 16 candidate snapshot. It retains the exact upstream candidate membership,
  `market_rank` order, candidate records and quote records; it does not capture, join, filter,
  rank, score or persist anything.
- Each item exposes exactly six unrounded quote observations: provider `change_pct`,
  `price_vs_open_pct`, `price_vs_prev_close_pct`, `session_range_pct`, provider
  `turnover_rate_pct`, and provider `volume_ratio`. Percentage values remain percentage points.
  Missing optional quote fields stay `None` with no imputation or substitute change signal.
- The immutable default policy uses `strong_move_pct=3.0`,
  `high_turnover_rate_pct=3.0`, and `high_volume_ratio=1.5`. It produces only the stable,
  descriptive flag order `STRONG_UP_MOVE`, `STRONG_DOWN_MOVE`, `HIGH_TURNOVER`, and
  `HIGH_VOLUME_RATIO`; flags never alter candidates.
- Diagnostics expose upstream readiness/blockers plus per-signal availability, item-level and
  aggregate completeness, and flagged-item counts. A blocked Task 16 snapshot maps to the sole
  scanner blocker `CANDIDATE_SNAPSHOT_NOT_READY`; a ready-empty snapshot remains scan-ready with
  no artificial 100% coverage.
- Sina fallback quotes with unavailable turnover rate and volume ratio remain scan-ready; those
  two observations are simply `None`. No IntradayScore, RealTimeScore, Top100, Top20,
  cross-sectional ranking, near-limit or liquidity detection, minute bars, scheduler, polling,
  API, CLI, Vue scanner UI, or persistence was added.

## Task 17 Verification

- `tests/realtime` — PASS (91 tests), including signal formula and units, missingness, provider
  versus derived change separation, inclusive thresholds, stable flag ordering, rank/membership
  preservation, readiness, availability accounting, determinism and scanner dependency boundaries.
- Canonical root validation — PASS (405 backend tests; 88% coverage); Ruff, mypy, frontend type
  check, lint, 34 Vitest tests and production build all pass.

## Next Task

No subsequent task has been started.

## Roadmap

- Tasks 00–05: project foundation, configuration, domain models, provider boundary,
  storage and local API/frontend foundation.
- Tasks 06–08: structural universe, dated risk/quality semantics and bounded RAW daily
  price collection.
- Task 08A: monorepo project-structure refactor (complete).
- Task 09: Fundamentals / Valuation / Industry (complete).
- Task 10: Factor Preprocessing (complete).
- Task 11: Five Factor Families (complete).
- Task 12: BaseScore (complete).
- Task 12A: Daily Selection API + Vue (complete).
- Task 13: Deterministic Explanation & Risk (complete).
- Task 14: Realtime Market Data Foundation (complete).
- Task 15: Realtime Candidate Foundation (complete).
- Task 16: Realtime Candidate Snapshot Join (complete).
- Task 17: Realtime Light Scanner Foundation (complete).
