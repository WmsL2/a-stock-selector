"""Safe public configuration contract tests."""

from collections.abc import Iterator

from fastapi.testclient import TestClient


def test_public_config_returns_only_explicit_non_sensitive_fields(
    client: TestClient,
) -> None:
    """Configuration response comes from an allowlist rather than a full dump."""
    response = client.get("/api/config/public")
    assert response.status_code == 200
    body = response.json()
    assert body["app"]["timezone"] == "Asia/Shanghai"
    assert body["selection"]["top_n"] > 0
    assert "quality" in body["factors"]
    forbidden = {"token", "secret", "password", "cookie", "credential", "api_key"}
    assert not (forbidden & set(_keys(body)))


def _keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).casefold()
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)
