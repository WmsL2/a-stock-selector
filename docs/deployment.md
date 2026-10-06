# Local Deployment and Operations

## Supported deployment model

This is a localhost-first, single-user/local-runtime application. Backend and frontend run as separate processes during development, and mutable runtime data stays local. The repository does not bundle public-production infrastructure, a static web server, or a reverse proxy.

## Prerequisites

Use Windows PowerShell, Python 3.12, a repository-root `.venv`, and Node/npm for the frontend.

## First-time setup

From the repository root, install the backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

Install frontend dependencies:

```powershell
Push-Location frontend
npm install
Pop-Location
```

## Development start

Start each process in its own terminal:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

Or start both PowerShell terminals:

```powershell
.\scripts\start-dev.ps1
```

Stop development by closing or stopping the spawned backend/frontend terminals or processes.

## Backend health check

The backend listens on `127.0.0.1:8000`. Check local application and storage health with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

The semantic fields are `status = ok`, `application = a-stock-selector`, and `storage = ready`. This health endpoint checks local application/storage readiness; it does not call an upstream market-data provider or perform a network health check.

## Frontend and API routing

The frontend API client uses the relative base `/api`. In development, Vite proxies `/api` to `http://127.0.0.1:8000`, so the local frontend reaches the local backend through that proxy.

Generate static frontend assets with:

```powershell
Push-Location frontend
npm run build
Pop-Location
```

The result is `frontend/dist/`. The repository does not provide a production static server or reverse-proxy configuration. If the static `dist` output is hosted outside Vite, that host must route `/api` to the FastAPI backend.

## Runtime state

`runtime/` contains local mutable state such as collected Parquet/DuckDB data, logs and research artifacts. Treat it as data that may need local backup according to the operator's own policy; no backup/restore mechanism is bundled. Deleting runtime data is not source uninstall and may remove collected evidence and persisted research snapshots.

## Data and network behavior

Application startup does not automatically download full-market data. Collection and refresh are explicit, manual operations. API reads and frontend pages do not imply background scheduling, and the application performs no autonomous trading.

## Validation before use

Run:

```powershell
.\scripts\test-all.ps1
```

See [final acceptance](acceptance.md) for the acceptance rule and local smoke procedure.

## Troubleshooting

- Missing `.venv`: create or restore the repository-root Python 3.12 virtual environment before backend installation or startup.
- Missing frontend `node_modules`: run `npm install` in `frontend/`.
- Port 8000 occupied: stop the process already listening on the local backend port before running `start-backend.ps1`.
- Frontend URL differs: use the address printed by Vite, which can select a different available port.
- Frontend cannot reach `/api`: confirm the backend is running at `127.0.0.1:8000`.
- Static `dist` host cannot reach the API: configure that external host to route `/api` to FastAPI.
- Local runtime/storage unavailable: restore local runtime availability before relying on API results.
