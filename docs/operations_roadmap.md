# Production / Data Operations Roadmap

Baseline: `04ff8235ed3e55fc115a442396e84ade67c8fdcb`

Task00–60 remains completed/frozen. This separate roadmap does not reopen those
tasks and is not Task61. It covers local data collection and operator workflows
for the A-share research application.

| Item | Scope | Status |
| --- | --- | --- |
| OPS01 — Decouple selection readiness from optional adjusted-return backfill | Refresh required risk, financial, industry, and valuation inputs without synchronous HFQ collection. | Completed |
| OPS02 — Provider timeout and fallback hardening | Bound provider waits and review fallback behavior. | Planned |
| OPS03 — Observable bounded progress and resumable operator batches | Make bounded batch progress and continuation observable. | Planned |
| OPS04 — First-time data initialization workflow | Define an explicit local initialization sequence. | Planned |
| OPS05 — Daily operator workflow and preflight | Define daily local operation and input preflight. | Planned |
| OPS06 — Production/data-operations acceptance | Validate the completed local operations workflow against agreed evidence. | Planned |

## OPS01 contract and source gate

`selection prepare-inputs`, `selection refresh-current`, and the refresh phase of
`selection daily` collect exact-date current risk and required financial,
industry, and valuation evidence. They skip adjusted-return collection with an
explicit not-requested report, then re-audit repository factor-input membership.

Factor-input membership remains `industry AND (financial OR valuation)`.
Adjusted returns remain optional and do not block official upstream readiness.
Already stored adjusted returns remain available to daily and realtime factor
and scoring logic. Generic all-slow-input refreshes retain adjusted returns by
default. Explicit `daily collect-adjusted-returns` and
`daily collect-structural-adjusted-returns` remain available.

OPS01 changes orchestration only. Provider timeout/retry/fallback policies,
concurrency, progress/resume UX, scheduling, factor formulas, ranking, frontend,
API, trading, and cloud deployment are outside this source gate.

## OPS01 verification

Focused validation passed 98 tests, and the broader selection/collection slice
passed 488 tests. Canonical validation passed with 1,079 backend tests in both
normal and coverage runs, 91% coverage, Ruff clean, and mypy clean across 123
source files. Frontend type-check and lint passed; Vitest passed 16 files and
99 tests; the production build passed with its existing chunk-size warning.

The bounded live `selection prepare-inputs --limit 1` smoke passed on
2026-10-07. It refreshed exact-date risk, collected financial, industry, and
valuation evidence for `000595.SZ`, and increased eligible factor-input
coverage from 152 to 153. Its transcript contained no HFQ adjusted-return
request or fallback evidence and explicitly reported that adjusted-return
refresh was skipped as optional. Generic all-slow-input and explicit
adjusted-return workflows remain supported.

OPS02–OPS06 remain Planned.
