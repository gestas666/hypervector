"""Restart-safe provider-bound exits from completed one-minute profit locks."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    ProfitLockTrigger,
    evaluate_profit_lock_path,
)
from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.multi_asset_live_protocols import (
    CohortTelemetryProtocol,
    MultiAssetEngineProtocol,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    entry_provider_strategy_id,
    position_side,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.sol_range_onset_state import SolLiveState

_MINUTE_MS = 60_000


class CohortProfitLockController:
    """Close open lifecycles only from their explicitly bound lock policy."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        telemetry: CohortTelemetryProtocol,
        required_plan_symbols: frozenset[str] = frozenset(),
    ) -> None:
        """Bind exact symbol engines and the durable decision boundary."""
        if not symbols or set(symbols) != set(engines):
            raise MultiAssetLiveRunnerError(
                "profit-lock controller symbols and engines must agree"
            )
        self._symbols = symbols
        self._engines = engines
        self._telemetry = telemetry
        if not required_plan_symbols.issubset(symbols):
            raise MultiAssetLiveRunnerError(
                "profit-lock required-plan symbols exceed controller scope"
            )
        self._required_plan_symbols = required_plan_symbols
        self._cycle_degraded = False

    @property
    def cycle_degraded(self) -> bool:
        """Report whether the current cycle lacked required causal candles."""
        return self._cycle_degraded

    def actions(
        self,
        *,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        entry_prices: Mapping[str, float],
        market_bars: Mapping[str, tuple[CohortMarketBar, ...]],
        excluded_symbols: set[str],
    ) -> tuple[set[str], tuple[RoutingAction, ...]]:
        """Return journaled close actions from exact completed-bar prefixes."""
        self._cycle_degraded = False
        closing: set[str] = set()
        actions: list[RoutingAction] = []
        for symbol in self._symbols:
            if symbol in excluded_symbols:
                continue
            action = self._action(
                symbol, observed_ms, reference_prices, entry_prices, market_bars
            )
            if action is not None:
                closing.add(symbol)
                actions.append(action)
        return closing, tuple(actions)

    def _action(
        self,
        symbol: str,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        entry_prices: Mapping[str, float],
        market_bars: Mapping[str, tuple[CohortMarketBar, ...]],
    ) -> RoutingAction | None:
        identity = self._identity(symbol)
        if identity is None:
            return None
        plan, provider, side, entry_oid, opened_at_ms = identity
        decision = self._decision(
            plan=plan,
            provider=provider,
            symbol=symbol,
            side=side,
            entry_oid=entry_oid,
            opened_at_ms=opened_at_ms,
            observed_ms=observed_ms,
            entry_price=entry_prices.get(symbol),
            market_bars=market_bars.get(symbol, ()),
        )
        if decision is None:
            return None
        mark = _positive_price(reference_prices.get(symbol), "reference price", symbol)
        return RoutingAction(
            "close",
            provider,
            symbol,
            side,
            _integer(decision.get("decision_time_ms"), "decision_time_ms"),
            mark,
            exit_reason="completed_bar_profit_lock",
        )

    def _identity(
        self, symbol: str
    ) -> tuple[BoundExecutionPlan, str, str, int, int] | None:
        snapshot = self._engines[symbol].snapshot
        plan = snapshot.execution_plan
        if snapshot.state is not SolLiveState.OPEN:
            return None
        if plan is None:
            if symbol in self._required_plan_symbols:
                raise MultiAssetLiveRunnerError(
                    f"{symbol} profit-lock lifecycle lacks its bound execution plan"
                )
            return None
        if plan.profit_lock_policy != "completed_bar_trailing":
            return None
        side = position_side(snapshot.position_size_signed)
        if side is None or snapshot.entry_oid is None or snapshot.opened_at_ms is None:
            raise MultiAssetLiveRunnerError(
                f"{symbol} profit lock lacks exact lifecycle identity"
            )
        return (
            plan,
            entry_provider_strategy_id(plan.strategy_id),
            side,
            snapshot.entry_oid,
            snapshot.opened_at_ms,
        )

    def _decision(
        self,
        *,
        plan: BoundExecutionPlan,
        provider: str,
        symbol: str,
        side: str,
        entry_oid: int,
        opened_at_ms: int,
        observed_ms: int,
        entry_price: float | None,
        market_bars: tuple[CohortMarketBar, ...],
    ) -> Mapping[str, object] | None:
        decision_id = f"{symbol}:{entry_oid}:profit_lock_exit"
        recorded = self._telemetry.recorded_profit_lock_decision(decision_id)
        if recorded is not None:
            _validate_recorded(
                recorded,
                plan,
                provider,
                symbol,
                side,
                entry_oid,
                opened_at_ms,
                observed_ms,
                entry_price,
            )
            return recorded
        entry = _positive_price(entry_price, "entry price", symbol)
        bars = self._lifecycle_bars(symbol, opened_at_ms, observed_ms, market_bars)
        if bars is None:
            return None
        state = evaluate_profit_lock_path(_policy(plan), side, bars, entry)
        if state.trigger is None:
            return None
        payload = _decision_payload(
            plan, provider, symbol, side, entry_oid, entry, state.trigger
        )
        self._telemetry.emit_profit_lock_decision(payload)
        return payload

    def _lifecycle_bars(
        self,
        symbol: str,
        opened_at_ms: int,
        observed_ms: int,
        bars: tuple[CohortMarketBar, ...],
    ) -> tuple[CohortMarketBar, ...] | None:
        first = opened_at_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
        last = (observed_ms - _MINUTE_MS) // _MINUTE_MS * _MINUTE_MS
        if last < first:
            return ()
        expected = tuple(range(first, last + _MINUTE_MS, _MINUTE_MS))
        scoped = tuple(bar for bar in bars if first <= bar.timestamp_ms <= last)
        actual = tuple(bar.timestamp_ms for bar in scoped)
        if actual == expected and all(bar.symbol == symbol for bar in scoped):
            return scoped
        reason = (
            f"{symbol} profit lock missing completed bars: "
            f"expected={len(expected)} observed={len(scoped)}"
        )
        self._telemetry.emit_poll_degraded(source="profit_lock_candles", reason=reason)
        self._cycle_degraded = True
        return None


def _policy(plan: BoundExecutionPlan) -> ProfitLockPolicy:
    values = (
        plan.profit_lock_activation_bps,
        plan.profit_lock_floor_bps,
        plan.profit_lock_giveback_bps,
    )
    if any(value is None for value in values):
        raise MultiAssetLiveRunnerError("bound profit-lock policy is incomplete")
    return ProfitLockPolicy(
        "provider_completed_bar_trailing",
        float(values[0]),
        float(values[1]),
        float(values[2]),
    )


def _decision_payload(
    plan: BoundExecutionPlan,
    provider: str,
    symbol: str,
    side: str,
    entry_oid: int,
    entry_price: float,
    trigger: ProfitLockTrigger,
) -> dict[str, object]:
    return {
        "decision_id": f"{symbol}:{entry_oid}:profit_lock_exit",
        "lifecycle_id": f"{symbol}:{entry_oid}",
        "strategy_id": provider,
        "symbol": symbol,
        "side": side,
        "outcome": "exit",
        "exit_reason": "completed_bar_profit_lock",
        "decision_time_ms": trigger.trigger_timestamp_ms + _MINUTE_MS,
        "trigger_bar_timestamp_ms": trigger.trigger_timestamp_ms,
        "activation_timestamp_ms": trigger.activation_timestamp_ms,
        "entry_price": entry_price,
        "trigger_reference_price": trigger.reference_price,
        "stop_price": trigger.stop_price,
        "best_completed_price": trigger.best_completed_price,
        "profit_lock_policy": plan.profit_lock_policy,
        "profit_lock_activation_bps": plan.profit_lock_activation_bps,
        "profit_lock_floor_bps": plan.profit_lock_floor_bps,
        "profit_lock_giveback_bps": plan.profit_lock_giveback_bps,
    }


def _validate_recorded(
    payload: Mapping[str, object],
    plan: BoundExecutionPlan,
    provider: str,
    symbol: str,
    side: str,
    entry_oid: int,
    opened_at_ms: int,
    observed_ms: int,
    entry_price: float | None,
) -> None:
    expected = {
        "decision_id": f"{symbol}:{entry_oid}:profit_lock_exit",
        "lifecycle_id": f"{symbol}:{entry_oid}",
        "strategy_id": provider,
        "symbol": symbol,
        "side": side,
        "outcome": "exit",
        "exit_reason": "completed_bar_profit_lock",
        "profit_lock_policy": plan.profit_lock_policy,
        "profit_lock_activation_bps": plan.profit_lock_activation_bps,
        "profit_lock_floor_bps": plan.profit_lock_floor_bps,
        "profit_lock_giveback_bps": plan.profit_lock_giveback_bps,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise MultiAssetLiveRunnerError(
            "persisted profit-lock exit conflicts with open lifecycle"
        )
    _validate_recorded_boundaries(payload, opened_at_ms, observed_ms)
    expected_entry = _positive_price(entry_price, "entry price", symbol)
    recorded_entry = _positive_price(payload.get("entry_price"), "entry price", symbol)
    if not math.isclose(expected_entry, recorded_entry, rel_tol=1e-12):
        raise MultiAssetLiveRunnerError(
            "persisted profit-lock exit conflicts with venue entry price"
        )
    for key in ("trigger_reference_price", "stop_price", "best_completed_price"):
        _positive_price(payload.get(key), key.replace("_", " "), symbol)


def _validate_recorded_boundaries(
    payload: Mapping[str, object],
    opened_at_ms: int,
    observed_ms: int,
) -> None:
    decision_time_ms = _integer(payload.get("decision_time_ms"), "decision_time_ms")
    if not opened_at_ms < decision_time_ms <= observed_ms:
        raise MultiAssetLiveRunnerError(
            "persisted profit-lock exit has an invalid causal boundary"
        )
    trigger_ms = _integer(
        payload.get("trigger_bar_timestamp_ms"), "trigger_bar_timestamp_ms"
    )
    activation_ms = _integer(
        payload.get("activation_timestamp_ms"), "activation_timestamp_ms"
    )
    if decision_time_ms != trigger_ms + _MINUTE_MS or trigger_ms < activation_ms:
        raise MultiAssetLiveRunnerError(
            "persisted profit-lock exit has an invalid trigger boundary"
        )


def _positive_price(value: object, label: str, symbol: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAssetLiveRunnerError(f"{symbol} profit lock lacks a {label}")
    price = float(value)
    if not math.isfinite(price) or price <= 0.0:
        raise MultiAssetLiveRunnerError(f"{symbol} profit lock has invalid {label}")
    return price


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MultiAssetLiveRunnerError(
            f"persisted profit-lock {label} must be an integer"
        )
    return value
