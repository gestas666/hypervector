"""Strict provider-symbol-direction profit-lock overrides."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
from typing import cast

from hypervector.live.cohort_execution_plan import (
    ProfitLockPolicy,
    ProviderExecutionContract,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

_POLICIES = frozenset({"none", "completed_bar_trailing"})
_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True)
class CohortProfitLockOverride:
    """One exact directional profit-lock policy layered on a provider contract."""

    symbol: str
    side: str
    policy: ProfitLockPolicy
    activation_bps: float | None = None
    floor_bps: float | None = None
    giveback_bps: float | None = None

    def __post_init__(self) -> None:
        """Reject partial, unsupported, or non-directional overrides."""
        if not self.symbol.strip() or self.side not in _SIDES:
            raise MultiAssetLiveConfigError(
                "provider profit_lock_overrides require symbol and long/short side"
            )
        values = (self.activation_bps, self.floor_bps, self.giveback_bps)
        if self.policy not in _POLICIES:
            raise MultiAssetLiveConfigError("unsupported profit_lock_overrides policy")
        if self.policy == "none":
            if any(value is not None for value in values):
                raise MultiAssetLiveConfigError(
                    "disabled profit_lock_overrides cannot define parameters"
                )
            return
        if any(value is None for value in values):
            raise MultiAssetLiveConfigError(
                "enabled profit_lock_overrides require activation, floor, and giveback"
            )
        activation, floor, _ = (_positive(value) for value in values)
        if floor > activation:
            raise MultiAssetLiveConfigError(
                "profit_lock_overrides floor cannot exceed activation"
            )

    def apply(self, contract: ProviderExecutionContract) -> ProviderExecutionContract:
        """Return the base contract with only this lock policy replaced."""
        return replace(
            contract,
            profit_lock_policy=self.policy,
            profit_lock_activation_bps=self.activation_bps,
            profit_lock_floor_bps=self.floor_bps,
            profit_lock_giveback_bps=self.giveback_bps,
        )

    def as_payload(self) -> dict[str, object]:
        """Return the exact configuration payload for telemetry."""
        payload: dict[str, object] = {"policy": self.policy}
        for key, value in (
            ("activation_bps", self.activation_bps),
            ("floor_bps", self.floor_bps),
            ("giveback_bps", self.giveback_bps),
        ):
            if value is not None:
                payload[key] = value
        return payload


def provider_profit_lock_overrides(
    value: object,
) -> tuple[CohortProfitLockOverride, ...]:
    """Parse nested symbol-side profit-lock override tables."""
    if value is None:
        return ()
    symbols = _mapping(value, "provider profit_lock_overrides")
    overrides: list[CohortProfitLockOverride] = []
    for symbol, sides in symbols.items():
        for side, raw_policy in _mapping(sides, "profit_lock_overrides symbol").items():
            policy = _mapping(raw_policy, "profit_lock_overrides side")
            overrides.append(_override(symbol, side, policy))
    return tuple(overrides)


def grouped_profit_lock_payload(
    overrides: tuple[CohortProfitLockOverride, ...],
) -> dict[str, dict[str, dict[str, object]]]:
    """Group normalized overrides by symbol and side for telemetry."""
    grouped: dict[str, dict[str, dict[str, object]]] = {}
    for override in overrides:
        grouped.setdefault(override.symbol, {})[override.side] = override.as_payload()
    return grouped


def _override(
    symbol: str,
    side: str,
    values: Mapping[str, object],
) -> CohortProfitLockOverride:
    allowed = {"policy", "activation_bps", "floor_bps", "giveback_bps"}
    unknown = set(values) - allowed
    if unknown:
        raise MultiAssetLiveConfigError(
            f"profit_lock_overrides contain unsupported fields: {sorted(unknown)}"
        )
    policy = values.get("policy")
    if not isinstance(policy, str):
        raise MultiAssetLiveConfigError("profit_lock_overrides policy must be text")
    return CohortProfitLockOverride(
        symbol=symbol,
        side=side,
        policy=cast(ProfitLockPolicy, policy),
        activation_bps=_optional_number(values.get("activation_bps")),
        floor_bps=_optional_number(values.get("floor_bps")),
        giveback_bps=_optional_number(values.get("giveback_bps")),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MultiAssetLiveConfigError(f"{label} must be a TOML table")
    return value


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAssetLiveConfigError("profit_lock_overrides values must be numeric")
    return _positive(float(value))


def _positive(value: float | None) -> float:
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise MultiAssetLiveConfigError(
            "profit_lock_overrides values must be positive and finite"
        )
    return value
