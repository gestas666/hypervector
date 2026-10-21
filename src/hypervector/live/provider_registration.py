"""What one live signal provider declares, and the profile checks it implies.

A provider declares only what its signal can compute and bind: the completed-bar
clock it reads, the symbols it evaluates, the sides it emits, the position
interaction it implements, whether it is observe-only, and the anchors its
intents carry. A profile row that asks for something the signal cannot compute
is refused. Stops, targets, holds, entry delays, sizing and execution scope
belong to the profile; the generic loader and ``live validate`` bound them
(taker IOC, sizing ceilings, stop inside liquidation, STOP beside the ledger,
authority flags), and no performance or strategy gate is added here
(SRS_HV1_NO_GATES).

Registrations are collected in ``hypervector.live.provider_registry``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import pandas as pd

from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.provider_evaluation import IntentBatch

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import ProviderExecutionContract
    from hypervector.live.multi_asset_live_config import (
        MultiAssetLiveConfig,
        StrategyProviderConfig,
    )

# Completed-bar clocks the cohort poller builds from its shared one-minute feed.
POLLER_SIGNAL_TIMEFRAMES = ("1m", "5m", "15m")
POSITION_POLICIES = frozenset({"enter_and_close", "flat_entry_only"})
_BOTH_SIDES = frozenset({"long", "short"})


class ProviderIntentCollectorProtocol(Protocol):
    """Uniform completed-bar provider interface used by the cohort poller."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate unseen completed bars after the causal boundary."""
        ...


class ProviderCollectorFactory(Protocol):
    """Build one provider's collector from its validated profile row."""

    def __call__(
        self,
        provider: StrategyProviderConfig,
        config: MultiAssetLiveConfig,
    ) -> ProviderIntentCollectorProtocol:
        """Return the collector the poller calls for every configured symbol."""
        ...


@dataclass(frozen=True)
class ProviderCapability:
    """What a provider's signal can compute and bind.

    ``symbols`` of None means the signal evaluates any symbol the profile
    enables. ``sides`` are the directions its intents can carry. An observe-only
    provider never emits intents, so its profile row may not grant execution
    symbols. ``stop_anchor`` and ``target_anchor`` say whether its intents carry
    a structural stop anchor and an absolute target anchor.
    """

    symbols: frozenset[str] | None = None
    sides: frozenset[str] = _BOTH_SIDES
    position_policies: frozenset[str] = POSITION_POLICIES
    observer_only: bool = False
    stop_anchor: bool = False
    target_anchor: bool = False

    def __post_init__(self) -> None:
        """Reject a declaration that no profile row could satisfy."""
        if self.symbols is not None and (
            not self.symbols
            or any(not isinstance(value, str) or not value.strip() for value in self.symbols)
        ):
            raise ValueError("provider capability symbols must be non-empty text")
        if not self.sides or not self.sides.issubset(_BOTH_SIDES):
            raise ValueError("provider capability sides must contain long and/or short")
        if not self.position_policies or not self.position_policies.issubset(
            POSITION_POLICIES
        ):
            raise ValueError("provider capability position policies are unsupported")
        for name in ("observer_only", "stop_anchor", "target_anchor"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"provider capability {name} must be boolean")


@dataclass(frozen=True)
class ProviderRegistration:
    """One provider's identity, signal clock, readiness lookback and collector."""

    strategy_id: str
    signal_timeframe: str
    readiness_lookback_minutes: int
    collector_factory: ProviderCollectorFactory
    capability: ProviderCapability = ProviderCapability()

    def __post_init__(self) -> None:
        """Reject an identity, clock or lookback the poller cannot serve."""
        if not isinstance(self.strategy_id, str) or (
            not self.strategy_id or self.strategy_id != self.strategy_id.strip()
        ):
            raise ValueError("provider strategy_id must be non-empty trimmed text")
        if self.signal_timeframe not in POLLER_SIGNAL_TIMEFRAMES:
            raise ValueError(
                "provider signal_timeframe must be one of "
                f"{', '.join(POLLER_SIGNAL_TIMEFRAMES)}"
            )
        lookback = self.readiness_lookback_minutes
        if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
            raise ValueError("provider readiness_lookback_minutes must be positive")
        if not callable(self.collector_factory):
            raise ValueError("provider collector_factory must be callable")
        if not isinstance(self.capability, ProviderCapability):
            raise ValueError("provider capability must be a ProviderCapability")


def binds_signal_anchors(
    execution: ProviderExecutionContract,
    *,
    stop_anchor: bool,
    target_anchor: bool = False,
) -> bool:
    """Return whether the exits need only the anchors the signal's intents carry.

    A structural stop binds each entry's stop_anchor and an absolute target its
    target_anchor, so a signal without them cannot use those policies; a signal
    that carries a target_anchor cannot bind a static target.
    """
    stop_bound = stop_anchor or execution.stop_policy == "fixed_bps"
    target_bound = (execution.target_policy == "absolute_anchor") == target_anchor
    return stop_bound and target_bound


def validate_provider_capability(
    provider: StrategyProviderConfig,
    registration: ProviderRegistration,
) -> None:
    """Refuse a profile row that asks for what the registered signal cannot do."""
    capability = registration.capability
    name = provider.strategy_id
    if provider.timeframe != registration.signal_timeframe:
        raise MultiAssetLiveConfigError(
            f"provider {name} reads the {registration.signal_timeframe} signal "
            f"clock; profile timeframe is {provider.timeframe}"
        )
    if capability.symbols is not None and not set(provider.symbols).issubset(
        capability.symbols
    ):
        raise MultiAssetLiveConfigError(
            f"provider {name} evaluates only {sorted(capability.symbols)}"
        )
    if not provider.sides.issubset(capability.sides):
        raise MultiAssetLiveConfigError(
            f"provider {name} emits only {sorted(capability.sides)}"
        )
    if provider.position_policy not in capability.position_policies:
        raise MultiAssetLiveConfigError(
            f"provider {name} implements position policies "
            f"{sorted(capability.position_policies)}"
        )
    if capability.observer_only and provider.execution_symbols:
        raise MultiAssetLiveConfigError(
            f"provider {name} is observe-only and cannot hold execution symbols"
        )
    if not binds_signal_anchors(
        provider.execution,
        stop_anchor=capability.stop_anchor,
        target_anchor=capability.target_anchor,
    ):
        raise MultiAssetLiveConfigError(
            f"provider {name} execution needs anchors its intents do not carry: "
            f"stop_anchor={capability.stop_anchor}, "
            f"target_anchor={capability.target_anchor}"
        )
