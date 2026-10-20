"""Signal capabilities for versioned multi-asset routes reused by successors.

A provider validator refuses only what its signal cannot compute or bind: the
symbols it evaluates, its signal clock, the sides it emits, the position
interaction it implements, the anchors its intents carry, and observer-only
scope. Stops, targets, holds, entry delays, execution scope and exit-policy
combinations belong to the profile; the generic loader and the runtime
validator bound them (SRS_HV1_NO_GATES).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    HIP3_SNDK_FRESH15_V4_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import ProviderExecutionContract
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig


HULK_BIDIRECTIONAL_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
_BOTH_SIDES = frozenset({"long", "short"})
_CORE_SYMBOLS = frozenset({"BTC", "ETH", "SOL", "HYPE"})


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


def validate_reused_route_contract(provider: StrategyProviderConfig) -> None:
    """Reject a known route whose declared scope its signal cannot compute."""
    if provider.strategy_id == HULK_BIDIRECTIONAL_STRATEGY:
        _validate_hulk_bidirectional(provider)
    elif provider.strategy_id == HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY:
        _validate_fresh15(
            provider, {"xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"}, "fresh15 commodity"
        )
    elif provider.strategy_id == HIP3_INDEX_FRESH15_V3_STRATEGY:
        _validate_fresh15(provider, {"xyz:SP500", "xyz:SPCX"}, "fresh15 index v3")
    elif provider.strategy_id == HIP3_SNDK_FRESH15_V4_STRATEGY:
        _validate_fresh15(provider, {"xyz:SNDK"}, "SNDK fresh15 v4")


def _validate_hulk_bidirectional(provider: StrategyProviderConfig) -> None:
    valid = (
        bool(provider.symbols)
        and set(provider.symbols).issubset(_CORE_SYMBOLS)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "30m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=True)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "bidirectional Hulk requires core symbols, both emitted sides, the "
            "30m signal, opposite-entry close, and no absolute target"
        )


def _validate_fresh15(
    provider: StrategyProviderConfig,
    valid_symbols: set[str],
    label: str,
) -> None:
    valid = (
        bool(provider.symbols)
        and set(provider.symbols).issubset(valid_symbols)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            f"{label} requires symbols within {sorted(valid_symbols)}, both "
            "emitted sides, the 15m signal, opposite-entry close, a fixed stop, "
            "and no absolute target"
        )
