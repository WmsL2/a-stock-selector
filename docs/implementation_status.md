# Implementation Status

## Current Task

Task 13 - Explanation & Risk

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
- `scripts/test-all.ps1` — PASS: 308 backend tests, 88% coverage, Ruff, mypy,
  frontend type check, lint, 29 Vitest tests and production build all completed.
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
  (308 passed; one third-party TestClient deprecation warning).
- Backend coverage (from `backend/`):
  `..\\.venv\\Scripts\\python.exe -m pytest --cov=stock_selector --cov-report=term-missing`
  — PASS (308 passed, 88% coverage).
- Backend static checks (from `backend/`): `..\\.venv\\Scripts\\ruff.exe check .` and
  `..\\.venv\\Scripts\\mypy.exe src` — PASS.
- Frontend validation (from `frontend/`): `npm install`, `npm run type-check`, `npm run lint`,
  `npm run test` — PASS (29 passed), and `npm run build` — PASS.
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
- Realtime scanner / engine
- Minute bars
- Intraday factors
- IntradayScore
- RealTimeScore
- Replay engine
- Backtest
- Factor research
- Scheduler

## Next Task

Task 14 - Realtime Market Data Foundation

Task 14 NOT STARTED.

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
- Task 14: Realtime Market Data Foundation (not started).
