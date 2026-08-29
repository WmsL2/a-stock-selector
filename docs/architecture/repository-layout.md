# Repository Layout

The workspace is intentionally small and uses five top-level product areas:

- `backend/`: Python package, tests, backend configuration and packaging metadata.
- `frontend/`: Vue application and frontend tests.
- `runtime/`: ignored local generated data, logs and snapshots.
- `docs/`: project-level architecture and development documentation.
- `scripts/`: portable PowerShell development entry points.

Runtime dependency direction is strictly one-way:

```text
Frontend -> HTTP -> FastAPI -> Quant Core -> Repository -> Runtime storage
```

The frontend never imports backend files at runtime, and backend code does not read frontend sources. `runtime/` is not a Python package; it stores Parquet and DuckDB state only.
