"""Pydantic models for application configuration."""

import math
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictConfigModel(BaseModel):
    """Base model that rejects unknown configuration fields."""

    model_config = ConfigDict(extra="forbid")


class AppConfig(StrictConfigModel):
    """Application-wide settings."""

    name: str = "A Stock Selector"
    timezone: str = "Asia/Shanghai"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a timezone recognized by the Python standard library."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value


class UniverseConfig(StrictConfigModel):
    """Parameters that define the future A-share stock universe."""

    include_sh_main: bool = True
    include_sz_main: bool = True
    include_chinext: bool = True
    include_star_market: bool = True
    include_bse: bool = True
    min_listing_days: int = Field(default=0, ge=0)
    exclude_st: bool = True
    exclude_delisting_period: bool = True
    exclude_suspended: bool = True
    liquidity_filter_enabled: bool = False
    min_avg_turnover_20d: float = Field(default=0.0, ge=0)


class FactorGroupConfig(StrictConfigModel):
    """Enablement and normalized weight for one factor group."""

    enabled: bool = True
    weight: float = Field(ge=0, le=1)


class FactorsConfig(StrictConfigModel):
    """Weight configuration for the supported future factor groups."""

    quality: FactorGroupConfig = FactorGroupConfig(weight=0.30)
    value: FactorGroupConfig = FactorGroupConfig(weight=0.25)
    growth: FactorGroupConfig = FactorGroupConfig(weight=0.20)
    momentum: FactorGroupConfig = FactorGroupConfig(weight=0.15)
    low_volatility: FactorGroupConfig = FactorGroupConfig(weight=0.10)

    @model_validator(mode="after")
    def validate_enabled_weights(self) -> Self:
        """Require enabled factor weights to be normalized to one."""
        groups = (
            self.quality,
            self.value,
            self.growth,
            self.momentum,
            self.low_volatility,
        )
        enabled_groups = [group for group in groups if group.enabled]
        if not enabled_groups:
            raise ValueError("At least one factor group must be enabled")
        weight_sum = sum(group.weight for group in enabled_groups)
        if not math.isclose(weight_sum, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("Enabled factor weights must sum to 1.0")
        return self


class SelectionConfig(StrictConfigModel):
    """Selection output-size settings."""

    top_n: int = Field(default=20, gt=0)
    watchlist_n: int = Field(default=10, ge=0)
    industry_classification: str = "证监会行业分类标准（2012）"

    @field_validator("industry_classification")
    @classmethod
    def validate_industry_classification(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("industry_classification must not be empty")
        return normalized


class RealtimeConfig(StrictConfigModel):
    """Reserved real-time system settings without market-data behavior."""

    enabled: bool = True
    snapshot_interval_seconds: int = Field(default=30, ge=5)
    freshness_normal_max_seconds: int = Field(default=60, gt=0)
    freshness_warning_max_seconds: int = Field(default=120, gt=0)

    @model_validator(mode="after")
    def validate_freshness_thresholds(self) -> Self:
        """Require an unambiguous normal, warning, then stale policy."""
        if self.freshness_warning_max_seconds <= self.freshness_normal_max_seconds:
            raise ValueError("freshness warning threshold must exceed normal threshold")
        return self


class LoggingConfig(StrictConfigModel):
    """Standard-library logging settings."""

    level: str = "INFO"
    console_enabled: bool = True
    file_enabled: bool = True
    filename: str = "a-stock-selector.log"
    max_bytes: int = Field(default=10_485_760, gt=0)
    backup_count: int = Field(default=5, ge=0)

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        """Normalize and validate a conventional logging level."""
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Unsupported logging level: {value}")
        return normalized

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Allow only a plain filename within the configured logs directory."""
        path = Path(value)
        if (
            not value
            or path.is_absolute()
            or path.name != value
            or "/" in value
            or "\\" in value
        ):
            raise ValueError("Logging filename must be a simple filename")
        return value


class Settings(StrictConfigModel):
    """Top-level application settings."""

    app: AppConfig = Field(default_factory=AppConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    factors: FactorsConfig = Field(default_factory=FactorsConfig)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    realtime: RealtimeConfig = Field(default_factory=RealtimeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
