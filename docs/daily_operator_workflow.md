# Daily operator workflow

Run the preflight with the existing project virtual environment. `-B` avoids
writing Python bytecode as part of normal operator use.

```powershell
.\venv\Scripts\python.exe -B -m stock_selector selection daily-preflight
```

The command is strictly read-only for application-managed runtime data. It does
not create a catalog or directories, call a provider, collect or refresh data,
score, rank, export research artifacts, or run official selection. It reports
the configured timezone and one `as_of` instant. It does not probe provider
health: `Provider checked: NO` means only that no probe was made.

| Exit code | Meaning |
| --- | --- |
| `0` | `READY`: current upstream membership evidence is complete. |
| `1` | `ERROR`: configuration or existing local storage could not be evaluated safely. |
| `2` | CLI usage error. |
| `3` | `BLOCKED`: evaluation succeeded, but authoritative readiness blockers remain. |

`READY` permits a human to decide whether to run official selection. It does
not guarantee a nonempty ranked result: point-in-time usable values and
scoreability are evaluated only by official selection. `selection run-current`
can itself exit `0` when official selection is blocked, so read its diagnostics.

## Daily decision path

1. Run `selection daily-preflight` before any current-date operation. Rerun it
   after local evidence, configuration, or the business date changes.
2. For a cold repository or `no_structural_members`, follow the
   [first-time initialization runbook](first_time_data_initialization.md). Do
   not create empty runtime state merely to make preflight pass.
3. For `risk_state_coverage_incomplete`, do not use stale risk evidence as a
   substitute. Resolve the provider/data path outside preflight, then rerun it.
4. For `eligible_factor_input_coverage_incomplete`, an operator may choose a
   bounded `selection prepare-inputs --limit <1-100> --progress` run. It still
   refreshes risk for the entire current structural universe before doing its
   limited slow-input work. Do not precede it with a duplicate
   `risk collect-current` call.
5. `selection refresh-current` can scan all currently missing inputs and is not
   the default daily action. Use it only after a deliberate operator decision.
6. `no_risk_eligible_members` means complete current risk evidence excluded all
   structural members. Do not run official selection as a workaround.
7. HFQ adjusted-return evidence remains optional for upstream readiness. Its
   absence is not a preflight blocker.
8. Only after `READY` and explicit human approval may an operator separately
   run `selection run-current`.

Normal daily checks, recovery, and retries must preserve all existing valid local market
data and research artifacts. Never delete or reset runtime data to recover from a
preflight error.

An interrupted collection has no durable checkpoint. Recompute actual missing
evidence before retrying; a cursor is only an ordering aid. Record `EMPTY` and
`FAILED` separately, because neither establishes coverage.

At the end of an operator run, retain the preflight output, exit code, `as_of`,
timezone, blockers, any actual collection reports, failure/empty counts, the
explicit human selection decision, and any official-selection diagnostics or
artifact paths. When the configured timezone date differs from Asia/Shanghai,
the preflight reports this boundary because current-risk providers use a
Shanghai-date contract; it does not substitute a date or infer a trading day.
