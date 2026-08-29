"""Local application boundary for building the current structural universe."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_selector.config.models import Settings
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe.builder import AshareUniverseBuilder
from stock_selector.universe.models import UniverseSnapshot


class CurrentUniverseService:
    """Combine local instrument metadata with configured structural policy."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._builder = AshareUniverseBuilder()

    def build_current(self, as_of: date | None = None) -> UniverseSnapshot:
        """Build current structural membership in the configured application timezone."""
        effective_as_of = as_of or datetime.now(
            ZoneInfo(self._settings.app.timezone)
        ).date()
        return self._builder.build(
            self._repository.load_instruments(),
            self._settings.universe,
            effective_as_of,
        )
