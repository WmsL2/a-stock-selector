# Final Acceptance

## Baseline

Task60 starts from `5748fd70e314eb21deff09f4a37ebfa509932ce8`, the completed and remote-verified Task59 commit.

## Product acceptance

The accepted local research product provides:

- daily selection and realtime selection workflows;
- deterministic explainability and visible readiness/blocker evidence;
- persisted research snapshots and history;
- effectiveness analysis, including exact-rank and rank-cutoff research;
- stability, filtering, comparison and export;
- preserved-result behavior and protection against stale request races.

Final offline acceptance does not require live market-data collection.

## Product boundary acceptance

The accepted scope excludes buy/sell recommendations, positions, position sizing, capital management, portfolio construction or optimization, rebalance logic, transaction-cost/slippage simulation, NAV/PnL, portfolio-level backtesting, brokerage integration, and automated/live trading.

## Automated acceptance

Run the canonical command from the repository root:

```powershell
.\scripts\test-all.ps1
```

Acceptance requires exit code `0`. The script runs backend pytest, backend pytest with coverage, Ruff, mypy, frontend type-check, frontend lint, Vitest, and the frontend production build.

Task60 final canonical acceptance PASS: backend pytest 1048 passed; coverage pytest 1048 passed with 91% coverage; Ruff PASS; mypy PASS for 123 source files; frontend type-check PASS; frontend lint PASS; Vitest PASS (16 files / 99 tests); and frontend production build PASS. Canonical exit code was `0`. Task60 is documentation-only, so these results confirm no unexpected regression.

Task60 local smoke acceptance PASS: `GET /api/health` returned `status: ok`, `application: a-stock-selector`, and `storage: ready`; the Vite development server at its printed local URL returned HTTP 200; and Vite `/api/health` proxy returned the same health semantics. These checks did not invoke provider, collection, refresh, or live-market-data endpoints, and do not claim browser automation.

## Local smoke acceptance

In terminal 1, start the backend:

```powershell
.\scripts\start-backend.ps1
```

Then check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected semantic fields are `status: ok`, `application: a-stock-selector`, and `storage: ready`.

In terminal 2, start the frontend:

```powershell
.\scripts\start-frontend.ps1
```

Open the URL printed by Vite. Accept when the frontend loads, navigation renders, and local API-backed pages can reach the backend. This is a manual smoke step and does not require triggering live provider collection.

## Repository hygiene acceptance

- No generated runtime data, credentials or tokens are committed.
- Task60 makes no `backend/src` or `frontend/src` change.
- Task60 makes no backend/frontend test or dependency change.
- Task60 introduces no deployment-infrastructure expansion.

## Final release decision

PASS only when the documentation source audit passes, canonical validation exits `0`, local smoke evidence is acceptable, the staged/commit scope is exact, and remote verification passes.
