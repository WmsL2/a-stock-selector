# First-time local data initialization

This runbook initializes local research data without running official daily
selection. It is a bounded operator workflow, not a background job. Preserve
existing `runtime/` data: do not delete databases, Parquet files, or research
artifacts as part of ordinary initialization.

## What each state means

- Storage initialized means directories and the DuckDB catalog exist. It does
  not mean market data has been collected.
- Research data populated means some local evidence has been persisted; its
  coverage can still be incomplete.
- Official daily selection ready requires a current structural universe,
  complete exact-date risk coverage, and complete required factor inputs for
  risk-eligible members. Successful status command exit code only means the
  audit ran; inspect its metrics and blockers.

## Phase 0–3: preflight, storage, and instrument master

Run configuration checks first:

```powershell
uv run --project backend python -m stock_selector config check
uv run --project backend python -m stock_selector config paths
uv run --project backend python -m stock_selector storage status
```

`storage status` initializes local directories/catalog if absent, but makes no
provider request and does not populate them.

Preview an instrument snapshot before any replacement:

```powershell
uv run --project backend python -m stock_selector data instruments-sync
```

The default mode fetches once, validates five-board representation, reads the
stored master, and prints a diff summary. It never replaces the master and
never collects daily, realtime, risk, financial, industry, or valuation data.

After obtaining trustworthy independent reference counts, explicitly apply a
snapshot with operator-selected floors. Do not copy these placeholders as
market-size assertions:

```powershell
uv run --project backend python -m stock_selector data instruments-sync --apply `
  --expected-min-total <TOTAL> `
  --expected-min-board sh_main=<COUNT> `
  --expected-min-board sz_main=<COUNT> `
  --expected-min-board chinext=<COUNT> `
  --expected-min-board star=<COUNT> `
  --expected-min-board bse=<COUNT>
```

Apply requires every positive board floor. It refuses empty, duplicate,
missing-board, undersized, removal, board-shrink, or existing identity-change
candidates. A successful apply replaces only the master and performs readback.
If catalog refresh/readback fails after the atomic Parquet swap, the command
fails and the final state is uncertain: inspect the local master/catalog before
retrying. It does not guarantee rollback. New listings and safe name/status
updates are allowed; delisting reconciliation is a separate future workflow.

Then audit the derived current structural universe:

```powershell
uv run --project backend python -m stock_selector universe status
```

Current structural coverage is not proof of historical point-in-time usability
or a survivorship-safe historical universe.

## Phase 4–5: required slow inputs

Use finite current-structural batches. The cursor orders one scan only; it is
not a durable checkpoint. After interruption, membership drift, `EMPTY`, or
`FAILED`, recompute missing evidence from the repository rather than resuming
blindly from an old cursor.

```powershell
uv run --project backend python -m stock_selector fundamentals collect-structural-core --limit <1-500>
uv run --project backend python -m stock_selector fundamentals collect-structural-valuation --limit <1-20>
uv run --project backend python -m stock_selector refresh structural-factor-input-status
uv run --project backend python -m stock_selector refresh structural-missing-slow-inputs --limit <1-100> --progress
```

Financial records are point-in-time records and obey `available_at`; do not use
future filings. Industry is effective-interval evidence and valuation is dated
observation evidence. Current factor-input membership is `industry AND
(financial OR valuation)`, but stored symbol membership alone is not proof of
as-of usability.

## Phase 6–7: optional price evidence

RAW history is explicit and bounded by operator-supplied symbols and inclusive
dates; do not request all-market history in one command. RAW close is not an
adjusted series.

```powershell
uv run --project backend python -m stock_selector daily collect --symbols <SYMBOLS> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
uv run --project backend python -m stock_selector daily collect-adjusted-returns --symbols <UP-TO-20-SYMBOLS> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
```

HFQ return evidence is separate from RAW storage, optional for official
readiness, and restricted to 20 symbols and 180 calendar days per explicit
request. Existing HFQ evidence remains usable by existing factor/scoring logic.

## Phase 8–10: risk, coverage, and handoff

Only when the external current-risk provider is available, collect the complete
current structural snapshot:

```powershell
uv run --project backend python -m stock_selector risk collect-current
uv run --project backend python -m stock_selector selection coverage-status
uv run --project backend python -m stock_selector selection input-status
```

Risk is current-date only. Never fabricate risk, backfill it to historical
dates, or use stale risk as exact-date coverage. If the provider is blocked,
preserve existing data, report readiness as NO, and continue only independent
offline research-data work whose prerequisites exist.

`selection prepare-inputs` already refreshes risk; do not precede it with a
duplicate risk refresh. It and `selection refresh-current` are official-input
workflows, not automatic first-time initialization or an instruction to run
daily selection. Finish by recording actual coverage/blockers and hand off to
an operator; do not run official selection automatically.

## Warm start and recovery

For a warm repository, audit first, preview master changes, retain all valid
persisted evidence, and target only current missing evidence. A provider error
or validation error does not write the master. Interrupted runs can replay a
provider request at least once because no durable execution manifest exists;
inspect actual local state and recompute missing work. `EMPTY` and `FAILED`
results may remain missing and a completed scan is not equivalent to complete
coverage.
