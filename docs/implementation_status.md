# Implementation Status

## Current Task

Task 08A - Monorepo Project Structure Refactor

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

## Task 08A Verification

- `python -m pip install -e ".\\backend[dev]"` — PASS; the editable package remains
  `stock_selector` from `backend/src`.
- `python -m stock_selector config paths` — PASS from the workspace root; configuration
  resolves under `backend/config`, while data, logs and snapshots resolve under `runtime/`.
- `python -m stock_selector storage status` — PASS offline after the migration: 5,551
  instruments, 5 daily rows, 3 realtime rows and 909.4 KB retained.
- `scripts/test-all.ps1` — PASS: 207 backend tests, 86% coverage, Ruff, mypy, frontend
  type check, lint, Vitest and production build all completed successfully.
- Backend script smoke — PASS: localhost `/api/health`, `/api/storage/status` and `/docs`
  returned 200.
- Frontend script and Vite proxy smoke — PASS: localhost `/`, `/api/health` and
  `/api/storage/status` returned 200. Temporary local processes were stopped afterwards.

## Tests

- `python -m pip install -e ".[dev]"` — PASS
- `python -m stock_selector --help` — PASS
- `python -m stock_selector version` — PASS
- `python -m stock_selector config check` — PASS
- `python -m pytest` — PASS (206 passed)
- `python -m pytest --cov=stock_selector --cov-report=term-missing` — PASS
  (206 passed, 86% coverage)
- `ruff check .` — PASS
- `mypy src` — PASS
- `git diff --check` — PASS
- `cd frontend && npm install` — PASS
- `cd frontend && npm run type-check` — PASS
- `cd frontend && npm run lint` — PASS
- `cd frontend && npm run test` — PASS (23 passed)
- `cd frontend && npm run build` — PASS

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

## Not Implemented Yet

- Full historical risk-state collector
- Full-market daily data quality
- Long-no-trade detection
- Full-market scheduled daily refresh
- Trading-calendar gap detection
- Corporate-action-adjusted return series
- Full historical research dataset
- Fundamentals
- Valuation
- Industry classification
- Factor preprocessing
- Factor engine
- BaseScore
- Explanation engine
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

Task 09 - Fundamentals / Valuation / Industry

Task 09 NOT STARTED.

## Roadmap

- Tasks 00–05: project foundation, configuration, domain models, provider boundary,
  storage and local API/frontend foundation.
- Tasks 06–08: structural universe, dated risk/quality semantics and bounded RAW daily
  price collection.
- Task 08A: monorepo project-structure refactor (complete).
- Task 09: Fundamentals / Valuation / Industry (not started).
