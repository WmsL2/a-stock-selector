"""Tests for safe YAML configuration loading and validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from stock_selector.config.loader import ConfigurationError, deep_merge, load_settings
from stock_selector.config.models import (
    AppConfig,
    FactorGroupConfig,
    FactorsConfig,
    LoggingConfig,
    RealtimeConfig,
    Settings,
    UniverseConfig,
)


def test_default_project_config_loads() -> None:
    """The committed project YAML configuration loads successfully."""
    settings = load_settings()
    assert settings.app.timezone == "Asia/Shanghai"
    assert settings.universe.min_listing_days == 0
    assert settings.universe.include_bse is True
    assert settings.realtime.freshness_normal_max_seconds == 60
    assert settings.realtime.freshness_warning_max_seconds == 120
    assert settings.factors.quality.weight == 0.30
    assert settings.factors.value.weight == 0.25
    assert settings.factors.growth.weight == 0.20
    assert settings.factors.momentum.weight == 0.15
    assert settings.factors.low_volatility.weight == 0.10
    enabled_weights = [
        group.weight
        for group in (
            settings.factors.quality,
            settings.factors.value,
            settings.factors.growth,
            settings.factors.momentum,
            settings.factors.low_volatility,
        )
        if group.enabled
    ]
    assert sum(enabled_weights) == pytest.approx(1.0)


@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_factor_group_rejects_out_of_range_weight(weight: float) -> None:
    """Individual factor weights must stay between zero and one."""
    with pytest.raises(ValidationError):
        FactorGroupConfig(weight=weight)


def test_factors_reject_non_normalized_enabled_weights() -> None:
    """Enabled factor weights must sum to one."""
    with pytest.raises(ValidationError):
        FactorsConfig(low_volatility=FactorGroupConfig(weight=0.0))


def test_factors_reject_all_disabled() -> None:
    """At least one factor must remain enabled."""
    disabled = FactorGroupConfig(enabled=False, weight=0.0)
    with pytest.raises(ValidationError):
        FactorsConfig(
            quality=disabled,
            value=disabled,
            growth=disabled,
            momentum=disabled,
            low_volatility=disabled,
        )


def test_constraints_reject_invalid_values() -> None:
    """Numeric range constraints reject invalid engineering values."""
    with pytest.raises(ValidationError):
        UniverseConfig(min_listing_days=-1)
    with pytest.raises(ValidationError):
        UniverseConfig(min_avg_turnover_20d=-0.1)
    with pytest.raises(ValidationError):
        RealtimeConfig(snapshot_interval_seconds=4)
    with pytest.raises(ValidationError):
        RealtimeConfig(freshness_normal_max_seconds=120, freshness_warning_max_seconds=120)


def test_invalid_timezone_and_unknown_fields_are_rejected() -> None:
    """Timezone typos and unknown configuration keys cannot be ignored."""
    with pytest.raises(ValidationError):
        AppConfig(timezone="Invalid/Timezone")
    with pytest.raises(ValidationError):
        Settings.model_validate({"app": {"timzone": "Asia/Shanghai"}})


@pytest.mark.parametrize("filename", ["../x.log", "logs/x.log", "C:/logs/x.log"])
def test_logging_filename_must_be_simple(filename: str) -> None:
    """The log file cannot escape the configured logs directory."""
    with pytest.raises(ValidationError):
        LoggingConfig(filename=filename)


def test_numeric_logging_level_raises_validation_error() -> None:
    """Pydantic rejects a non-string log level instead of leaking TypeError."""
    with pytest.raises(ValidationError):
        LoggingConfig(level=123)


def test_lowercase_logging_level_is_normalized() -> None:
    """Valid lowercase logging levels are normalized to uppercase."""
    config = LoggingConfig(level="info")
    assert config.level == "INFO"


def test_unsupported_logging_level_raises_validation_error() -> None:
    """Unknown logging levels remain configuration validation errors."""
    with pytest.raises(ValidationError):
        LoggingConfig(level="TRACE")


def test_missing_yaml_file_raises_configuration_error(tmp_path: Path) -> None:
    """Missing required YAML files fail explicitly."""
    with pytest.raises(ConfigurationError, match="not found"):
        load_settings(tmp_path)


def test_invalid_yaml_raises_configuration_error(tmp_path: Path) -> None:
    """YAML syntax errors retain a clear configuration failure."""
    _write_config_files(tmp_path, default="app: [unterminated")
    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_settings(tmp_path)


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    """A YAML sequence cannot serve as a configuration document root."""
    _write_config_files(tmp_path, default="- not-a-mapping")
    with pytest.raises(ConfigurationError, match="must be a mapping"):
        load_settings(tmp_path)


def test_numeric_log_level_from_yaml_raises_configuration_error(tmp_path: Path) -> None:
    """A YAML type error is wrapped at the public configuration boundary."""
    _write_config_files(tmp_path, default="logging:\n  level: 123\n")
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        load_settings(tmp_path)


def test_invalid_utf8_yaml_raises_configuration_error(tmp_path: Path) -> None:
    """Invalid UTF-8 input cannot escape as a decoding traceback."""
    _write_config_files(tmp_path)
    (tmp_path / "default.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigurationError, match="Invalid UTF-8"):
        load_settings(tmp_path)


def test_deep_merge_preserves_nested_values() -> None:
    """Nested overrides preserve keys not mentioned by the override."""
    merged = deep_merge(
        {"logging": {"level": "INFO", "file_enabled": True}},
        {"logging": {"level": "DEBUG"}},
    )
    assert merged == {"logging": {"level": "DEBUG", "file_enabled": True}}


def _write_config_files(
    directory: Path,
    *,
    default: str = "app:\n  timezone: Asia/Shanghai\n",
) -> None:
    """Create the three required YAML files for loader failure tests."""
    (directory / "default.yaml").write_text(default, encoding="utf-8")
    (directory / "markets.yaml").write_text("universe: {}\n", encoding="utf-8")
    (directory / "factors.yaml").write_text("factors: {}\n", encoding="utf-8")
