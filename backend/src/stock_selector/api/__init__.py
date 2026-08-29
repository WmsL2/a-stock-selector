"""Local read-only HTTP API for the A Stock Selector application."""

from stock_selector.api.app import create_app

__all__ = ["create_app"]
