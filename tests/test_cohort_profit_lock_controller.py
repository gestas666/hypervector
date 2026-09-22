"""Causal and restart-safe contracts for provider-bound profit locks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

import pytest

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    ProviderExecutionContract,
)
import hypervector.live.cohort_route_cycle as route_cycle_module
from hypervector.live.cohort_profit_lock_controller import CohortProfitLockController
from multi_asset_live_runner_fixtures import execution_contract as _contract
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError
from hypervector.live.sol_range_onset_ledger import SOL_LIVE_EVENT_TYPES
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_PROVIDER = "range_onset_bidirectional_v1"
_SYMBOL = "SOL"
_OPENED_MS = 10_000


@dataclass
class _Engine:
    current: SolLiveSnapshot

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self.current


class _Telemetry:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, object]] = {}
        self.degraded: list[tuple[str, str]] = []

    def recorded_profit_lock_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        return self.decisions.get(decision_id)

    def emit_profit_lock_decision(self, payload: Mapping[str, object]) -> None:
        decision_id = str(payload["decision_id"])
        existing = self.decisions.get(decision_id)
        if existing is not None and existing != dict(payload):
            raise ValueError("conflicting profit-lock decision")
        self.decisions[decision_id] = dict(payload)

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        self.degraded.append((source, reason))


def _plan(*, enabled: bool = True) -> BoundExecutionPlan:
    values: dict[str, object] = {}
    if enabled:
        values = {
            "profit_lock_policy": "completed_bar_trailing",
            "profit_lock_activation_bps": 25.0,
            "profit_lock_floor_bps": 15.0,
            "profit_lock_giveback_bps": 10.0,
        }
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
        **values,
    ).bind(strategy_id=_PROVIDER, stop_anchor=None)


def _snapshot(*, enabled: bool = True) -> SolLiveSnapshot:
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=7,
        stop_oid=8,
        position_size_signed=1.0,
        opened_at_ms=_OPENED_MS,
        execution_plan=_plan(enabled=enabled),
    )


def _bar(
    timestamp_ms: int,
    *,
    body: float,
    high: float,
    low: float,
) -> CohortMarketBar:
    return CohortMarketBar(_SYMBOL, timestamp_ms, body, high, low, body, 1.0)


def _actions(
    bars: tuple[CohortMarketBar, ...],
    *,
    snapshot: SolLiveSnapshot | None = None,
    telemetry: _Telemetry | None = None,
    observed_ms: int = 180_000,
) -> tuple[set[str], tuple[RoutingAction, ...]]:
    sink = telemetry or _Telemetry()
    controller = CohortProfitLockController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(snapshot or _snapshot())},
        telemetry=sink,
    )
    return controller.actions(
        observed_ms=observed_ms,
        reference_prices={_SYMBOL: 100.18},
        entry_prices={_SYMBOL: 100.0},
        market_bars={_SYMBOL: bars},
        excluded_symbols=set(),
    )


def test_disabled_profit_lock_has_no_execution_authority() -> None:
    """A legacy/default plan ignores even a path that would trigger a lock."""
    bars = (
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.2, high=100.25, low=100.1),
    )

    assert _actions(bars, snapshot=_snapshot(enabled=False)) == (set(), ())


def test_required_profit_lock_position_rejects_a_missing_bound_plan() -> None:
    """A restart cannot silently replace an entry-owned lock with defaults."""
    snapshot = replace(_snapshot(), execution_plan=None)
    controller = CohortProfitLockController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(snapshot)},
        telemetry=_Telemetry(),
        required_plan_symbols=frozenset({_SYMBOL}),
    )

    with pytest.raises(
        MultiAssetLiveRunnerError, match="lacks its bound execution plan"
    ):
        controller.actions(
            observed_ms=180_000,
            reference_prices={_SYMBOL: 100.18},
            entry_prices={_SYMBOL: 100.0},
            market_bars={_SYMBOL: ()},
            excluded_symbols=set(),
        )


def test_profit_lock_decision_is_an_explicit_ledger_event() -> None:
    """Durable lock decisions cannot be hidden in a generic heartbeat payload."""
    assert "profit_lock_decision" in SOL_LIVE_EVENT_TYPES


def test_completed_bar_lock_persists_before_returning_current_price_exit() -> None:
    """The prior-bar stop crossing becomes one journaled current-price action."""
    telemetry = _Telemetry()
    bars = (
        _bar(0, body=100.0, high=200.0, low=50.0),
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.2, high=100.25, low=100.1),
    )

    closing, actions = _actions(bars, telemetry=telemetry)

    assert closing == {_SYMBOL}
    assert actions[0].decision_time_ms == 180_000
    assert actions[0].reference_price == 100.18
    assert actions[0].exit_reason == "completed_bar_profit_lock"
    decision = telemetry.decisions[f"{_SYMBOL}:7:profit_lock_exit"]
    assert decision["trigger_bar_timestamp_ms"] == 120_000
    assert decision["decision_time_ms"] == 180_000


def test_unrecorded_lock_recomputes_when_a_completed_bar_is_corrected() -> None:
    """A later transport view may reveal a trigger before one is journaled."""
    telemetry = _Telemetry()
    initial = (
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.22, high=100.25, low=100.21),
    )
    corrected = (
        initial[0],
        _bar(120_000, body=100.22, high=100.25, low=100.19),
    )

    assert _actions(initial, telemetry=telemetry) == (set(), ())
    closing, actions = _actions(corrected, telemetry=telemetry)

    assert closing == {_SYMBOL}
    assert actions[0].exit_reason == "completed_bar_profit_lock"


def test_missing_lifecycle_bar_fails_closed_and_is_observable() -> None:
    """A candle gap cannot be interpreted as a harmless no-trigger path."""
    telemetry = _Telemetry()
    bars = (_bar(120_000, body=100.2, high=100.3, low=100.1),)

    controller = CohortProfitLockController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(_snapshot())},
        telemetry=telemetry,
    )
    assert controller.actions(
        observed_ms=180_000,
        reference_prices={_SYMBOL: 100.18},
        entry_prices={_SYMBOL: 100.0},
        market_bars={_SYMBOL: bars},
        excluded_symbols=set(),
    ) == (set(), ())
    assert telemetry.decisions == {}
    assert telemetry.degraded
    assert "missing completed bars" in telemetry.degraded[0][1]
    assert controller.cycle_degraded is True


def test_persisted_lock_exit_replays_when_candle_source_disappears() -> None:
    """Restart recovery cannot lose a causal lock decision already journaled."""
    telemetry = _Telemetry()
    bars = (
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.2, high=100.25, low=100.1),
    )
    assert _actions(bars, telemetry=telemetry)[0] == {_SYMBOL}

    closing, actions = _actions(
        (),
        telemetry=telemetry,
        observed_ms=240_000,
    )

    assert closing == {_SYMBOL}
    assert actions[0].decision_time_ms == 180_000


def test_persisted_future_lock_decision_fails_closed() -> None:
    """A restart cannot execute a journal row before its causal bar close."""
    telemetry = _Telemetry()
    bars = (
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.2, high=100.25, low=100.1),
    )
    assert _actions(bars, telemetry=telemetry)[0] == {_SYMBOL}

    with pytest.raises(MultiAssetLiveRunnerError, match="causal boundary"):
        _actions((), telemetry=telemetry, observed_ms=179_999)


def test_persisted_lock_rejects_corrupted_trigger_boundary() -> None:
    """Journal recovery validates the trigger bar rather than trusting its ID."""
    telemetry = _Telemetry()
    bars = (
        _bar(60_000, body=100.2, high=100.3, low=100.1),
        _bar(120_000, body=100.2, high=100.25, low=100.1),
    )
    assert _actions(bars, telemetry=telemetry)[0] == {_SYMBOL}
    decision_id = f"{_SYMBOL}:7:profit_lock_exit"
    telemetry.decisions[decision_id]["trigger_bar_timestamp_ms"] = 60_000

    with pytest.raises(MultiAssetLiveRunnerError, match="trigger boundary"):
        _actions((), telemetry=telemetry, observed_ms=240_000)


def test_required_plan_symbols_include_a_directional_profit_lock_override() -> None:
    """A bound lock must latch its fail-closed plan requirement.

    `provider_execution_contracts` resolves direction, then symbol, then provider;
    deriving required_plan_symbols from the provider entry alone let a symbol whose
    lock is bound per (provider, symbol, side) restart planless with the
    controller's lost-plan check disarmed.
    """
    locked = replace(
        _contract(),
        profit_lock_policy="completed_bar_trailing",
        profit_lock_activation_bps=100.0,
        profit_lock_floor_bps=25.0,
        profit_lock_giveback_bps=50.0,
    )
    contracts = {"hulk": _contract(), ("hulk", "SOL", "long"): locked}

    symbols = route_cycle_module._profit_lock_symbols(
        contracts,
        frozenset({("hulk", "SOL"), ("hulk", "BTC")}),
        frozenset({("hulk", "SOL", "long"), ("hulk", "BTC", "short")}),
    )

    assert symbols == frozenset({"SOL"})
