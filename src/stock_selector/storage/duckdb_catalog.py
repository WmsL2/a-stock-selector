"""DuckDB catalog that exposes Parquet source-of-truth files as external views."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import duckdb

from stock_selector.config.paths import AppPaths
from stock_selector.storage.errors import StorageIOError


class DuckDBCatalog:
    """Maintain metadata and read-only Parquet views with short-lived connections."""

    def __init__(self, paths: AppPaths) -> None:
        """Keep catalog path only; no database is created until initialize()."""
        self._database_path = paths.metadata_dir / "stock_selector.duckdb"
        self._processed_data_dir = paths.processed_data_dir

    @property
    def database_path(self) -> Path:
        """Return the catalog database location."""
        return self._database_path

    def initialize(self) -> None:
        """Create schema-version metadata and empty-or-external data views."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(self._initialize_connection)

    def refresh_views(self) -> None:
        """Point views at current Parquet files only after successful writes."""
        self._run(self._refresh_connection)

    def counts(self) -> tuple[int, int, int, int, int, datetime | None]:
        """Return row, symbol, snapshot, and latest-time aggregates from the views."""
        return self._run(self._count_connection)

    def schema_version(self) -> int:
        """Read the small catalog schema version marker."""
        return self._run(self._schema_version_connection)

    def _run(self, operation: Callable[[Any], "CatalogResult"]) -> "CatalogResult":
        """Execute one operation with a connection that is always closed."""
        connection = None
        try:
            connection = duckdb.connect(str(self._database_path))
            return operation(connection)
        except duckdb.Error as exc:
            raise StorageIOError(f"DuckDB catalog operation failed: {self._database_path}") from exc
        finally:
            if connection is not None:
                connection.close()

    def _initialize_connection(self, connection: Any) -> None:
        """Create only the catalog metadata table, then install data views."""
        connection.execute(
            "CREATE TABLE IF NOT EXISTS storage_metadata "
            "(schema_version INTEGER PRIMARY KEY)"
        )
        connection.execute("INSERT OR REPLACE INTO storage_metadata VALUES (1)")
        self._refresh_connection(connection)

    def _refresh_connection(self, connection: Any) -> None:
        """Install all external views with typed empty views where no data exists."""
        instrument_path = self._processed_data_dir / "instruments" / "instruments.parquet"
        daily_glob = self._processed_data_dir / "daily_bars" / "*.parquet"
        realtime_glob = self._processed_data_dir / "realtime_quotes" / "**" / "*.parquet"
        self._replace_view(
            connection,
            "instruments",
            instrument_path.exists(),
            _duckdb_path(instrument_path),
            "symbol VARCHAR, name VARCHAR, exchange VARCHAR, board VARCHAR, "
            "listing_date DATE, delisting_date DATE, status VARCHAR",
        )
        self._replace_view(
            connection,
            "daily_bars",
            any((self._processed_data_dir / "daily_bars").glob("*.parquet")),
            _duckdb_path(daily_glob),
            "symbol VARCHAR, trade_date DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
            "close DOUBLE, volume DOUBLE, amount DOUBLE, source VARCHAR",
        )
        self._replace_view(
            connection,
            "realtime_quotes",
            any((self._processed_data_dir / "realtime_quotes").rglob("*.parquet")),
            _duckdb_path(realtime_glob),
            "symbol VARCHAR, price DOUBLE, open DOUBLE, high DOUBLE, low DOUBLE, "
            "prev_close DOUBLE, volume DOUBLE, amount DOUBLE, change_pct DOUBLE, "
            "turnover_rate DOUBLE, volume_ratio DOUBLE, source_timestamp TIMESTAMPTZ, "
            "ingested_at TIMESTAMPTZ, source VARCHAR",
        )

    @staticmethod
    def _replace_view(
        connection: Any, name: str, available: bool, path: str, columns: str
    ) -> None:
        """Create an external parquet view or a shape-compatible empty view."""
        if available:
            connection.execute(
                f"CREATE OR REPLACE VIEW {name} AS "
                f"SELECT * FROM read_parquet('{path}')"
            )
        else:
            connection.execute(
                f"CREATE OR REPLACE VIEW {name} AS "
                f"SELECT {_typed_empty_columns(columns)} WHERE FALSE"
            )

    @staticmethod
    def _count_connection(connection: Any) -> tuple[int, int, int, int, int, datetime | None]:
        """Query aggregate coverage, never inferring it from filenames or mtimes."""
        daily_rows, daily_symbols = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM daily_bars"
        ).fetchone()
        realtime_rows, realtime_symbols, snapshots, latest_at = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol), COUNT(DISTINCT ingested_at), "
            "CAST(MAX(ingested_at) AS VARCHAR) FROM realtime_quotes"
        ).fetchone()
        return (
            int(daily_rows),
            int(daily_symbols),
            int(realtime_rows),
            int(realtime_symbols),
            int(snapshots),
            datetime.fromisoformat(latest_at) if latest_at is not None else None,
        )

    @staticmethod
    def _schema_version_connection(connection: Any) -> int:
        """Fetch the one supported catalog version."""
        result = connection.execute("SELECT schema_version FROM storage_metadata").fetchone()
        return int(result[0])


def _duckdb_path(path: Path) -> str:
    """Format a Windows-safe SQL path literal content for DuckDB."""
    return path.as_posix().replace("'", "''")


def _typed_empty_columns(columns: str) -> str:
    """Build a zero-row select list retaining each view's declared column types."""
    return ", ".join(
        f"CAST(NULL AS {column.rsplit(' ', maxsplit=1)[1]}) AS "
        f"{column.rsplit(' ', maxsplit=1)[0]}"
        for column in columns.split(", ")
    )


CatalogResult = TypeVar("CatalogResult")
