# Runtime State

`runtime/` contains generated local application state and is not business-source code.

- `data/` contains Parquet market datasets and the DuckDB catalog.
- `logs/` contains application logs.
- `snapshots/` contains local research snapshots.

These runtime files are ignored by Git. Keep this README (and optional `.gitkeep` placeholders) tracked, but never commit Parquet, DuckDB, credentials, tokens, or generated logs.
