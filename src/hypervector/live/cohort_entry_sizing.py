"""Explicit provider-symbol sizing policies for the shared live cohort."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.multi_asset_live_config_parsing import (
    MultiAssetLiveConfigError,
    mapping,
    number,
)

_FIELDS = frozenset({"margin_fraction", "max_notional_usd"})
_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True)
class CohortEntrySizing:
    """One configured provider-symbol margin and notional policy."""

    margin_fraction: float
    max_notional_usd: float

    def __post_init__(self) -> None:
        """Reject non-finite or economically malformed sizing inputs."""
        if (
            not math.isfinite(self.margin_fraction)
            or not 0.0 < self.margin_fraction <= 1.0
        ):
            raise ValueError("entry margin_fraction must be finite and in (0, 1]")
        if not math.isfinite(self.max_notional_usd) or self.max_notional_usd <= 0.0:
            raise ValueError("entry max_notional_usd must be finite and positive")

    def planned_notional(self, *, account_value_usd: float, leverage: float) -> float:
        """Return configured fractional notional bounded by the explicit cap."""
        if not math.isfinite(account_value_usd) or account_value_usd <= 0.0:
            raise ValueError("entry account value must be finite and positive")
        if not math.isfinite(leverage) or leverage <= 0.0:
            raise ValueError("entry leverage must be finite and positive")
        return min(
            account_value_usd * self.margin_fraction * leverage,
            self.max_notional_usd,
        )

    def as_payload(self) -> dict[str, float]:
        """Return a stable non-secret telemetry representation."""
        return {
            "margin_fraction": self.margin_fraction,
            "max_notional_usd": self.max_notional_usd,
        }


def provider_sizing_overrides(
    value: object,
) -> tuple[tuple[str, CohortEntrySizing], ...]:
    """Parse optional provider-symbol sizing policies from TOML."""
    if value is None:
        return ()
    rows = mapping(value, "provider sizing_overrides")
    overrides: list[tuple[str, CohortEntrySizing]] = []
    for raw_symbol, raw_policy in rows.items():
        symbol = raw_symbol.strip()
        policy = mapping(raw_policy, "provider sizing override")
        if not symbol or frozenset(policy) != _FIELDS:
            raise MultiAssetLiveConfigError(
                "provider sizing_overrides require symbol, margin_fraction, and max_notional_usd"
            )
        try:
            sizing = CohortEntrySizing(
                margin_fraction=number(policy, "margin_fraction"),
                max_notional_usd=number(policy, "max_notional_usd"),
            )
        except ValueError as exc:
            raise MultiAssetLiveConfigError(str(exc)) from exc
        overrides.append((symbol, sizing))
    return tuple(overrides)


def provider_directional_sizing_overrides(
    value: object,
) -> tuple[tuple[str, str, CohortEntrySizing], ...]:
    """Parse optional provider-symbol-side sizing policies from TOML."""
    if value is None:
        return ()
    rows = mapping(value, "provider directional_sizing_overrides")
    overrides: list[tuple[str, str, CohortEntrySizing]] = []
    for raw_symbol, raw_sides in rows.items():
        symbol = raw_symbol.strip()
        sides = mapping(raw_sides, "provider directional sizing override")
        if not symbol or not sides or not set(sides).issubset(_SIDES):
            raise MultiAssetLiveConfigError(
                "provider directional sizing requires a symbol and long/short policies"
            )
        for raw_side, raw_policy in sides.items():
            side = raw_side.strip()
            policy = mapping(raw_policy, "provider directional sizing policy")
            if frozenset(policy) != _FIELDS:
                raise MultiAssetLiveConfigError(
                    "provider directional sizing policies require "
                    "margin_fraction and max_notional_usd"
                )
            try:
                sizing = CohortEntrySizing(
                    margin_fraction=number(policy, "margin_fraction"),
                    max_notional_usd=number(policy, "max_notional_usd"),
                )
            except ValueError as exc:
                raise MultiAssetLiveConfigError(str(exc)) from exc
            overrides.append((symbol, side, sizing))
    return tuple(overrides)
