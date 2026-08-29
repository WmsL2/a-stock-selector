# A Stock Selector

个人使用的 A 股量化研究与选股系统，仅供研究与技术学习，不构成投资建议。

## Architecture

- `backend/` — Python 3.12 quant core, FastAPI, CLI, providers, storage, collection, universe, risk and quality.
- `frontend/` — Vue 3, TypeScript and Vite application using only the local HTTP API.
- `runtime/` — ignored local Parquet, DuckDB, logs and research snapshots.
- `docs/` — project architecture, development notes and implementation status.
- `scripts/` — root-level development and verification entry points.

Dependency direction is: Vue frontend → local HTTP API → FastAPI/quant core → repository → runtime storage.

## Quick Start

Create or retain a Python 3.12 virtual environment at the repository root, then install the backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

Install frontend dependencies:

```powershell
Push-Location frontend
npm install
Pop-Location
```

Start the backend, frontend, or both from any working directory:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
.\scripts\start-dev.ps1
```

Run the complete local validation suite:

```powershell
.\scripts\test-all.ps1
```

## Development and Runtime State

The backend package remains `stock_selector`; `backend/` is a repository-layout boundary, not a Python module prefix. Runtime state is stored under `runtime/` and is intentionally not committed. The project does not automatically download all-market history or start network collection.

Operational daily prices are currently RAW source-of-truth prices. They are not corporate-action-adjusted total-return history, and price-return factors must not silently treat them as such before a dedicated adjustment design exists.

## Project Status

Tasks 00–08 are complete. Task 08A establishes the monorepo structure. The next planned task is Task 09 — Fundamentals / Valuation / Industry; it has not started. The broader roadmap is documented in [implementation status](docs/implementation_status.md).
