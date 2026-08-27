"""Safe YAML configuration loading and validation."""

from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import ValidationError

from stock_selector.config.models import Settings
from stock_selector.config.paths import AppPaths


class ConfigurationError(Exception):
    """Raised when configuration files cannot be read or validated."""


def deep_merge(
    base: Mapping[str, object], override: Mapping[str, object]
) -> dict[str, object]:
    """Recursively merge mapping values while preserving unspecified keys."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def load_settings(config_dir: Path | None = None) -> Settings:
    """Load the three project YAML files and validate merged settings."""
    directory = config_dir.resolve() if config_dir is not None else _default_config_dir()
    merged: dict[str, object] = {}
    for filename in ("default.yaml", "markets.yaml", "factors.yaml"):
        merged = deep_merge(merged, _load_yaml_mapping(directory / filename))
    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc


def _default_config_dir() -> Path:
    """Return the default config directory from centralized project paths."""
    return AppPaths.from_project_root().config_dir


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    """Read one YAML mapping file with clear, chained failures."""
    try:
        with path.open(encoding="utf-8") as file:
            contents: object = yaml.safe_load(file)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file not found: {path}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Unable to read configuration file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"Invalid UTF-8 in configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in configuration file: {path}") from exc
    if not isinstance(contents, Mapping):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    if not all(isinstance(key, str) for key in contents):
        raise ConfigurationError(f"Configuration keys must be strings: {path}")
    return dict(contents)
