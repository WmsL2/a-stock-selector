"""Tests for idempotent project logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from stock_selector.config.models import LoggingConfig
from stock_selector.config.paths import AppPaths
from stock_selector.logging_config import PROJECT_LOGGER_NAME, configure_logging


@pytest.fixture(autouse=True)
def clear_project_logger() -> None:
    """Keep logging handlers isolated across tests."""
    _clear_handlers()
    yield
    _clear_handlers()


def test_console_and_file_handlers_are_created(tmp_path: Path) -> None:
    """Requested console and rotating-file handlers are configured."""
    paths = AppPaths.from_project_root(tmp_path)
    configure_logging(LoggingConfig(), paths)
    handlers = logging.getLogger(PROJECT_LOGGER_NAME).handlers
    assert any(type(handler) is logging.StreamHandler for handler in handlers)
    assert any(isinstance(handler, RotatingFileHandler) for handler in handlers)


def test_file_logging_creates_directory_and_writes_utf8(tmp_path: Path) -> None:
    """File logging creates the directory and preserves Chinese UTF-8 text."""
    paths = AppPaths.from_project_root(tmp_path)
    configure_logging(LoggingConfig(console_enabled=False), paths)
    logger = logging.getLogger(PROJECT_LOGGER_NAME)
    logger.info("配置加载成功")
    for handler in logger.handlers:
        handler.flush()
    log_file = paths.logs_dir / "a-stock-selector.log"
    assert log_file.is_file()
    assert "配置加载成功" in log_file.read_text(encoding="utf-8")


def test_reconfiguration_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """Repeated configuration remains idempotent."""
    paths = AppPaths.from_project_root(tmp_path)
    config = LoggingConfig()
    configure_logging(config, paths)
    first_count = len(logging.getLogger(PROJECT_LOGGER_NAME).handlers)
    configure_logging(config, paths)
    assert len(logging.getLogger(PROJECT_LOGGER_NAME).handlers) == first_count


def test_disabled_file_logging_does_not_create_log_file(tmp_path: Path) -> None:
    """No log directory or file is created when file logging is disabled."""
    paths = AppPaths.from_project_root(tmp_path)
    configure_logging(LoggingConfig(file_enabled=False), paths)
    assert not paths.logs_dir.exists()


def test_disabled_console_logging_omits_console_handler(tmp_path: Path) -> None:
    """Disabling console logging leaves no plain stream handler."""
    paths = AppPaths.from_project_root(tmp_path)
    configure_logging(
        LoggingConfig(console_enabled=False, file_enabled=False),
        paths,
    )
    handlers = logging.getLogger(PROJECT_LOGGER_NAME).handlers
    assert not any(type(handler) is logging.StreamHandler for handler in handlers)


def _clear_handlers() -> None:
    """Remove test-created handlers from the project logger."""
    logger = logging.getLogger(PROJECT_LOGGER_NAME)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
