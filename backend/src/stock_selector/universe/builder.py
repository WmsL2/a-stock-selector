"""Pure structural membership logic with no provider, storage, or clock access."""

from datetime import date

from stock_selector.config.models import UniverseConfig
from stock_selector.models import Board, Instrument
from stock_selector.universe.errors import UniverseDataError
from stock_selector.universe.models import (
    UniverseDecision,
    UniverseExclusionReason,
    UniverseSnapshot,
)

_BOARD_ENABLED = {
    Board.SH_MAIN: "include_sh_main",
    Board.SZ_MAIN: "include_sz_main",
    Board.CHINEXT: "include_chinext",
    Board.STAR: "include_star_market",
    Board.BSE: "include_bse",
}


class AshareUniverseBuilder:
    """Build an auditable structural universe at one caller-supplied date.

    Instrument ``status`` is deliberately not consulted: it is not a dated
    historical risk-state series and would introduce lookahead bias.
    """

    def build(
        self,
        instruments: tuple[Instrument, ...],
        config: UniverseConfig,
        as_of: date,
    ) -> UniverseSnapshot:
        """Return deterministic board and lifecycle decisions for every input."""
        _require_unique_symbols(instruments)
        decisions = tuple(
            self._decide(instrument, config, as_of)
            for instrument in sorted(instruments, key=lambda item: item.symbol)
        )
        return UniverseSnapshot(
            as_of=as_of,
            input_count=len(instruments),
            members=tuple(decision.symbol for decision in decisions if decision.included),
            decisions=decisions,
        )

    def _decide(
        self, instrument: Instrument, config: UniverseConfig, as_of: date
    ) -> UniverseDecision:
        reasons: list[UniverseExclusionReason] = []
        if _is_non_a_share_security(instrument):
            reasons.append(UniverseExclusionReason.NON_A_SHARE_SECURITY)
        enabled_field = _BOARD_ENABLED.get(instrument.board)
        if enabled_field is None:
            raise UniverseDataError("instrument board is not supported by universe policy")
        if not getattr(config, enabled_field):
            reasons.append(UniverseExclusionReason.BOARD_DISABLED)
        if as_of < instrument.listing_date:
            reasons.append(UniverseExclusionReason.NOT_YET_LISTED)
        if instrument.delisting_date is not None and as_of > instrument.delisting_date:
            reasons.append(UniverseExclusionReason.DELISTED)
        if (
            config.min_listing_days > 0
            and (as_of - instrument.listing_date).days < config.min_listing_days
        ):
            reasons.append(UniverseExclusionReason.MIN_LISTING_DAYS)
        return UniverseDecision(
            symbol=instrument.symbol,
            included=not reasons,
            reasons=tuple(reasons),
        )


def _require_unique_symbols(instruments: tuple[Instrument, ...]) -> None:
    symbols = tuple(instrument.symbol for instrument in instruments)
    if len(set(symbols)) != len(symbols):
        raise UniverseDataError("universe input contains duplicate symbols")


def _is_non_a_share_security(instrument: Instrument) -> bool:
    """Identify the verified STAR depositary-receipt code range from identity only."""
    code, _exchange = instrument.symbol.rsplit(".", maxsplit=1)
    return instrument.board is Board.STAR and code.startswith("689")
