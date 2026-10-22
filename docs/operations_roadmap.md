# Production / Data Operations Roadmap

Baseline: `04ff8235ed3e55fc115a442396e84ade67c8fdcb`

Task00–60 remains completed/frozen. This separate roadmap does not reopen those
tasks and is not Task61. It covers local data collection and operator workflows
for the A-share research application.

| Item | Scope | Status |
| --- | --- | --- |
| OPS01 — Decouple selection readiness from optional adjusted-return backfill | Refresh required risk, financial, industry, and valuation inputs without synchronous HFQ collection. | Completed |
| OPS02 — Provider timeout and fallback hardening | Bound provider waits and review fallback behavior. | Completed |
| OPS03 — Observable bounded progress and resumable operator batches | Make bounded batch progress and continuation observable. | Completed |
| OPS04 — First-time data initialization workflow | Guarded instrument-master sync and bounded local initialization runbook. | Completed |
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

## OPS02 contract

Application-owned Requests network attempts use a 15-second connect/read timeout
while preserving third-party explicit timeouts and existing fallback/retry rules.
This timeout is per network attempt; it is not a total operation wall-clock
deadline across pagination, retries, backoff, streaming, DNS, or system behavior.

## OPS02 verification and external-provider gate exception

Focused timeout-adapter validation passed 44 tests, and provider regressions
passed 141 tests. Canonical validation passed with 1,091 backend tests in both
normal and coverage runs at 91% coverage. Ruff, mypy across 124 source files,
frontend type-check and lint, Vitest, and the production build passed.

The bounded HFQ failure-path live smoke exited 1 in approximately 3.3 seconds
after its permitted fallback and reported a finite application-level
`ProviderConnectionError`. The bounded current-risk live smoke exited 1 in
8.194 seconds after Eastmoney fell back to Sina and reported a finite
application-level `ProviderConnectionError`. Neither transcript exposed a raw
Requests/urllib3 traceback, `KeyboardInterrupt`, or sensitive URL.

OPS02 is completed under an explicit external-provider availability gate
exception: the current-risk smoke passes transport-failure handling only; it is
not a successful readiness collection. Successful live readiness under OPS02
remains unverified, and exact-date risk coverage remains blocked until an
external current-risk provider is available. No additional provider requests
are required to obtain a green exit code.

## OPS03 contract and verification

`--progress` is opt-in for `selection prepare-inputs`, `selection
refresh-current`, `selection daily`, `refresh structural-missing-slow-inputs`,
and `refresh structural-slow-inputs-sweep`. It emits flushed `RUN_STARTED`,
post-persistence `BATCH_COMPLETED`, and `RUN_FINISHED` events; `RUN_BLOCKED` or
`RUN_FAILED` identifies a non-successful terminal path without exposing a
provider exception. A handled per-symbol provider failure remains part of the
existing collection/report continuation semantics, whereas a fatal batch emits
no misleading completion event for that batch. `EMPTY` and `FAILED` remain
distinct and neither is persisted evidence.

The existing 20-symbol inner batches and 100-symbol outer batches remain in
place, along with each command's existing limit boundary. `selection
refresh-current` and `selection daily` may still process the complete missing
set in one invocation. A forward scan cursor is ordering only, not a durable
completion checkpoint: after failure, interruption, or an uncertain final write,
operators recompute missing work from authoritative repository evidence without
reusing the old cursor. Recovery can replay provider work at least once; OPS03
does not provide exactly-once execution, a durable manifest, or a database
schema. It adds no concurrency, provider retry, timeout, ranking, factor,
scoring, or selection-result behavior. Adjusted returns remain optional for
official readiness under OPS01; generic and explicit HFQ collection behavior and
exact-date risk-readiness requirements are unchanged.

Focused validation passed 208 tests and the collection/selection regression
passed 405 tests. Canonical validation passed with 1,093 tests in both pytest
runs and 91% coverage; Ruff passed, mypy passed across 124 source files,
frontend type-check and lint passed, Vitest passed 99 tests, and the production
build passed. No live OPS03 provider-success smoke was performed: completion is
based on deterministic offline tests and full canonical validation.

## OPS04 contract and verification

OPS04 adds the dedicated `data instruments-sync` command. It is preview-only by
default; replacement requires explicit `--apply`, an operator-supplied minimum
total count, and positive operator-supplied floors for all five supported
boards. Each candidate is validated before master replacement. Existing symbols
cannot silently disappear, board coverage cannot shrink, and existing exchange,
board, and listing-date identities are protected. Safe new listings and
permitted metadata updates remain supported. Each invocation performs one
provider fetch and no unrelated-domain collection. A successful apply performs
a full persisted-tuple readback verification. A pre-write failure preserves the
existing master. Parquet replacement and DuckDB catalog refresh are not one
atomic transaction, so a later catalog failure may leave persistence state
uncertain; the command does not promise rollback.

The service is located at
`backend/src/stock_selector/instrument_sync.py`, outside the collection layer,
so its repository orchestration preserves the collection-layer architecture.
The first-time initialization runbook is
`docs/first_time_data_initialization.md`. It defines cold, warm,
provider-blocked, and interrupted initialization/recovery procedures without an
implicit automatic full-market historical backfill. RAW collection and optional
HFQ collection remain separate. Exact-date current-risk requirements and
factor-input membership semantics remain unchanged, and optional HFQ remains
nonblocking for official selection readiness. OPS04 adds no scheduler, trading,
or background collection and makes no historical survivorship-safety claim.

OPS04 implementation baseline: `b9566aa1d032a4404ecc90f62bf6441e128b5cba`.
The roadmap baseline at the top of this document remains the historical
operations-roadmap baseline, `04ff8235ed3e55fc115a442396e84ade67c8fdcb`.

Canonical validation passed: backend pytest passed 1,118 tests with 12
warnings; backend coverage pytest passed 1,118 tests with 12 warnings and 91%
total backend coverage, including 97% coverage for `instrument_sync.py`. Ruff
passed. Mypy passed across 125 source files. Frontend type-check and lint
passed; Vitest passed 16 files / 99 tests; the frontend production build passed
with its existing chunk-size warning. The first canonical run exposed an
architecture-boundary violation, subsequently fixed by moving the service out
of `collection/`. The second run exposed a Windows pytest temporary-path
configuration problem. The final canonical run passed completely with an
isolated short relative `basetemp` path. No live OPS04 provider-success smoke
was performed; offline validation is not successful live data initialization.

OPS04 completion does not recover live current-risk provider availability. The
OPS02 external-provider limitation remains: no successful live provider
initialization is claimed, and exact-date risk coverage remains blocked until
an external current-risk provider is available.

OPS01–OPS04 are Completed. OPS05–OPS06 remain Planned. Task00–60 remains
frozen.
