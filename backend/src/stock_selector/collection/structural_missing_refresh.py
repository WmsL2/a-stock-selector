"""Pure missing-membership scan planning for bounded structural refreshes."""

from datetime import datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)


class StructuralMissingRefreshPlanRequest(DomainModel):
    as_of: datetime
    structural_symbols: tuple[str, ...]
    missing_structural_symbols: tuple[str, ...]
    limit: int
    start_after: str | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("structural_symbols")
    @classmethod
    def validate_structural(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "structural_symbols", allow_empty=False)

    @field_validator("missing_structural_symbols")
    @classmethod
    def validate_missing(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "missing_structural_symbols", allow_empty=True)

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("limit must be between 1 and 100")
        return value

    @field_validator("start_after")
    @classmethod
    def validate_start_after(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_membership(self) -> "StructuralMissingRefreshPlanRequest":
        structural = set(self.structural_symbols)
        if not set(self.missing_structural_symbols) <= structural:
            raise ValueError("missing_structural_symbols must be a structural subset")
        if self.start_after is not None and self.start_after not in structural:
            raise ValueError("start_after must be a current structural member")
        return self


class StructuralMissingRefreshPlan(DomainModel):
    as_of: datetime
    structural_symbols: tuple[str, ...]
    missing_structural_symbols: tuple[str, ...]
    limit: int
    start_after: str | None = None
    selected_symbols: tuple[str, ...]
    missing_structural_members: int
    missing_after_cursor: int
    selected_count: int
    selected_first_symbol: str | None
    selected_last_symbol: str | None
    has_more_missing_after_selection: bool
    next_start_after: str | None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("structural_symbols")
    @classmethod
    def validate_structural(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value, "structural_symbols", allow_empty=False)

    @field_validator("missing_structural_symbols", "selected_symbols")
    @classmethod
    def validate_symbol_tuples(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _validate_symbols(value, info.field_name or "symbols", allow_empty=True)

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        return StructuralMissingRefreshPlanRequest.validate_limit(value)

    @field_validator("start_after", "selected_first_symbol", "selected_last_symbol", "next_start_after")
    @classmethod
    def validate_optional_symbol(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_plan(self) -> "StructuralMissingRefreshPlan":
        request = StructuralMissingRefreshPlanRequest(
            as_of=self.as_of,
            structural_symbols=self.structural_symbols,
            missing_structural_symbols=self.missing_structural_symbols,
            limit=self.limit,
            start_after=self.start_after,
        )
        expected = _plan_values(request)
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError(f"{name} must match exact structural cursor planning")
        return self


class StructuralMissingRefreshPlanner:
    """Plan one finite missing-symbol scan without infrastructure dependencies."""

    def plan(self, request: StructuralMissingRefreshPlanRequest) -> StructuralMissingRefreshPlan:
        return StructuralMissingRefreshPlan.model_validate({
            "as_of": request.as_of,
            "structural_symbols": request.structural_symbols,
            "missing_structural_symbols": request.missing_structural_symbols,
            "limit": request.limit,
            "start_after": request.start_after,
            **_plan_values(request),
        })


def _plan_values(request: StructuralMissingRefreshPlanRequest) -> dict[str, object]:
    start_index = (
        0
        if request.start_after is None
        else request.structural_symbols.index(request.start_after) + 1
    )
    missing = set(request.missing_structural_symbols)
    candidates = tuple(symbol for symbol in request.structural_symbols[start_index:] if symbol in missing)
    selected = candidates[: request.limit]
    has_more = len(candidates) > len(selected)
    return {
        "selected_symbols": selected,
        "missing_structural_members": len(request.missing_structural_symbols),
        "missing_after_cursor": len(candidates),
        "selected_count": len(selected),
        "selected_first_symbol": selected[0] if selected else None,
        "selected_last_symbol": selected[-1] if selected else None,
        "has_more_missing_after_selection": has_more,
        "next_start_after": selected[-1] if has_more else None,
    }


def _validate_symbols(value: tuple[str, ...], field_name: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    for symbol in value:
        validate_symbol(symbol)
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise ValueError(f"{field_name} must be canonical, unique, and sorted")
    return value
