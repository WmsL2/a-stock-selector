"""Pure current-structural factor-input membership coverage audit."""

from datetime import datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)


class StructuralFactorInputCoverageRequest(DomainModel):
    """Already-loaded membership tuples and an explicit audit timestamp."""

    as_of: datetime
    structural_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("structural_symbols")
    @classmethod
    def validate_structural_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "structural_symbols", allow_empty=False)

    @field_validator("factor_input_symbols")
    @classmethod
    def validate_factor_input_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "factor_input_symbols", allow_empty=True)


class StructuralFactorInputCoverageReport(DomainModel):
    """Exact, deterministic partition of current structural membership."""

    as_of: datetime
    structural_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]
    covered_structural_symbols: tuple[str, ...]
    missing_structural_symbols: tuple[str, ...]
    nonstructural_factor_input_symbols: tuple[str, ...]
    structural_members: int
    stored_factor_input_symbols: int
    structural_factor_input_covered: int
    structural_factor_input_missing: int
    nonstructural_stored_factor_input_symbols: int
    first_missing_symbol: str | None
    last_missing_symbol: str | None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("structural_symbols")
    @classmethod
    def validate_structural_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "structural_symbols", allow_empty=False)

    @field_validator(
        "factor_input_symbols",
        "covered_structural_symbols",
        "missing_structural_symbols",
        "nonstructural_factor_input_symbols",
    )
    @classmethod
    def validate_symbol_tuples(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _validate_symbols(value, info.field_name or "symbol tuple", allow_empty=True)

    @field_validator("first_missing_symbol", "last_missing_symbol")
    @classmethod
    def validate_optional_symbol(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_report(self) -> "StructuralFactorInputCoverageReport":
        structural = set(self.structural_symbols)
        factor = set(self.factor_input_symbols)
        covered = tuple(sorted(structural & factor))
        missing = tuple(sorted(structural - factor))
        nonstructural = tuple(sorted(factor - structural))
        if (
            self.covered_structural_symbols != covered
            or self.missing_structural_symbols != missing
            or self.nonstructural_factor_input_symbols != nonstructural
        ):
            raise ValueError("coverage tuples must match the exact membership partition")
        if (
            self.structural_members != len(self.structural_symbols)
            or self.stored_factor_input_symbols != len(self.factor_input_symbols)
            or self.structural_factor_input_covered != len(covered)
            or self.structural_factor_input_missing != len(missing)
            or self.nonstructural_stored_factor_input_symbols != len(nonstructural)
        ):
            raise ValueError("coverage counts must match membership tuples")
        if self.structural_factor_input_covered > self.structural_members:
            raise ValueError("covered structural count cannot exceed structural members")
        if self.structural_factor_input_missing != (
            self.structural_members - self.structural_factor_input_covered
        ):
            raise ValueError("missing count must complement covered structural count")
        expected_first = missing[0] if missing else None
        expected_last = missing[-1] if missing else None
        if (self.first_missing_symbol, self.last_missing_symbol) != (
            expected_first,
            expected_last,
        ):
            raise ValueError("missing boundary metadata must match missing symbols")
        return self


class StructuralFactorInputCoverageAuditor:
    """Perform deterministic set arithmetic without infrastructure dependencies."""

    def audit(
        self, request: StructuralFactorInputCoverageRequest
    ) -> StructuralFactorInputCoverageReport:
        structural = set(request.structural_symbols)
        factor = set(request.factor_input_symbols)
        covered = tuple(sorted(structural & factor))
        missing = tuple(sorted(structural - factor))
        nonstructural = tuple(sorted(factor - structural))
        return StructuralFactorInputCoverageReport(
            as_of=request.as_of,
            structural_symbols=request.structural_symbols,
            factor_input_symbols=request.factor_input_symbols,
            covered_structural_symbols=covered,
            missing_structural_symbols=missing,
            nonstructural_factor_input_symbols=nonstructural,
            structural_members=len(request.structural_symbols),
            stored_factor_input_symbols=len(request.factor_input_symbols),
            structural_factor_input_covered=len(covered),
            structural_factor_input_missing=len(missing),
            nonstructural_stored_factor_input_symbols=len(nonstructural),
            first_missing_symbol=missing[0] if missing else None,
            last_missing_symbol=missing[-1] if missing else None,
        )


def _validate_symbols(
    value: tuple[str, ...], field_name: str, *, allow_empty: bool
) -> tuple[str, ...]:
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    for symbol in value:
        validate_symbol(symbol)
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise ValueError(f"{field_name} must be canonical, unique, and sorted")
    return value
