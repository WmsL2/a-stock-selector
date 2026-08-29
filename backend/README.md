# Backend

Python 3.12 backend for A Stock Selector. It contains the FastAPI read-only API, quant domain models, provider abstractions, local Parquet/DuckDB storage, bounded daily collection, structural universe, dated risk states and quality reporting.

Install from the workspace root with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

From this directory, run tests and tooling with `..\.venv\Scripts\python.exe -m pytest`, `..\.venv\Scripts\ruff.exe check .`, and `..\.venv\Scripts\mypy.exe src`. Runtime data remains outside this source tree at `../runtime/`.
