"""Application factory and OpenAPI contract tests."""

from fastapi.testclient import TestClient

from stock_selector import __version__


def test_app_factory_exposes_expected_metadata_and_openapi(client: TestClient) -> None:
    """The factory retains development documentation with explicit DTO schemas."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["info"] == {
        "title": "A Stock Selector API",
        "description": "Local read-only API for the A-share quantitative research application.",
        "version": __version__,
    }
    schemas = document["components"]["schemas"]
    for name in (
        "HealthResponse",
        "StorageStatusResponse",
        "InstrumentListResponse",
        "InstrumentResponse",
        "DailyBarsResponse",
        "RealtimeLookupResponse",
        "PublicConfigResponse",
        "UniverseStatusResponse",
        "QualityStatusResponse",
    ):
        assert name in schemas


def test_docs_are_available(client: TestClient) -> None:
    """Interactive local API docs remain enabled for the future frontend."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text
