"""Static boundary checks that keep the HTTP layer local and read-only."""

from pathlib import Path

from stock_selector.api.app import create_app
from stock_selector.config.paths import AppPaths


def test_api_has_no_provider_network_or_storage_engine_imports() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector"
    forbidden = (
        "import akshare",
        "from akshare",
        "import requests",
        "from requests",
        "import duckdb",
        "from duckdb",
        "import pyarrow",
        "from pyarrow",
        "from stock_selector.providers",
        "import stock_selector.providers",
    )
    for path in (root / "api").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden), path
    for path in (root / "storage").glob("*.py"):
        assert "import fastapi" not in path.read_text(encoding="utf-8"), path


def test_api_routes_are_get_only_and_cors_is_not_wildcard(tmp_path) -> None:  # type: ignore[no-untyped-def]
    application = create_app(AppPaths.from_project_root(tmp_path))
    api_routes = [
        route
        for included_router in application.routes
        if getattr(getattr(included_router, "include_context", None), "prefix", "")
        == "/api"
        for route in getattr(getattr(included_router, "original_router", None), "routes", ())
    ]
    assert api_routes
    for route in api_routes:
        assert set(route.methods or ()) <= {"GET", "HEAD"}
    middleware = "\n".join(repr(item) for item in application.user_middleware)
    assert "allow_origins=['*']" not in middleware
