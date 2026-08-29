"""Idempotent standard-library logging configuration."""

import logging
from logging.handlers import RotatingFileHandler

from stock_selector.config.models import LoggingConfig
from stock_selector.config.paths import AppPaths

PROJECT_LOGGER_NAME = "stock_selector"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(config: LoggingConfig, paths: AppPaths) -> None:
    """Configure the project logger with requested console and file handlers."""
    logger = logging.getLogger(PROJECT_LOGGER_NAME)
    logger.setLevel(config.level)
    logger.propagate = False
    _remove_handlers(logger)
    formatter = logging.Formatter(LOG_FORMAT)
    if config.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    if config.file_enabled:
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            paths.logs_dir / config.filename,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def _remove_handlers(logger: logging.Logger) -> None:
    """Close and remove only handlers owned by the project logger."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
