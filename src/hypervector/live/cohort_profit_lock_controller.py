"""Restart-safe provider-bound exits from completed one-minute profit locks."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    ProfitLockPathState,
    ProfitLockTrigger,
    evaluate_profit_lock_path,
)
from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_POLICY_IDS,
    BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
    DelayedComponentFloorResult,
    build_btc_hulk_component_floor_observations,
    component_floor_policy_payload,
    delayed_component_policy,
    evaluate_delayed_component_floor,
)
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.cohort_profit_lock_values import _positive_price, _integer, _text
from hypervector.live.cohort_adaptive_exit_controller import (
    adaptive_exit_action,
    retention_breakeven_requested,
)
from hypervector.live.cohort_adaptive_exit_policy import RETENTION_EXIT_POLICY
from hypervector.live.provider_evaluation import ProviderEvaluation
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
        self._breakeven_requests: frozenset[str] = frozenset()

    @property
    def cycle_degraded(self) -> bool:
        """Report whether the current cycle lacked required causal candles."""
        return self._cycle_degraded

    @property
    def breakeven_requests(self) -> frozenset[str]:
        """Symbols whose durable v2 state armed the profit floor during this cycle."""
        return self._breakeven_requests

    def actions(
        self,
        *,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        entry_prices: Mapping[str, float],
        market_bars: Mapping[str, tuple[CohortMarketBar, ...]],
        excluded_symbols: set[str],
        evaluations: tuple[ProviderEvaluation, ...] = (),
    ) -> tuple[set[str], tuple[RoutingAction, ...]]:
        """Return journaled close actions from exact completed-bar prefixes."""
        self._cycle_degraded = False
        closing: set[str] = set()
        actions: list[RoutingAction] = []
        breakeven: set[str] = set()
        for symbol in self._symbols:
            if symbol in excluded_symbols:
                continue
            action = self._action(
                symbol,
                observed_ms,
                reference_prices,
                entry_prices,
                market_bars,
                evaluations,
            )
            if action is not None:
                closing.add(symbol)
                actions.append(action)
            elif self._retention_bound(symbol) and retention_breakeven_requested(
                symbol=symbol,
                snapshot=self._engines[symbol].snapshot,
                entry_price=entry_prices.get(symbol),
                journal=self._telemetry.adaptive_exit_journal,
            ):
                breakeven.add(symbol)
        self._breakeven_requests = frozenset(breakeven)
        return closing, tuple(actions)

    def _action(
        self,
        symbol: str,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        entry_prices: Mapping[str, float],
        market_bars: Mapping[str, tuple[CohortMarketBar, ...]],
        evaluations: tuple[ProviderEvaluation, ...],
    ) -> RoutingAction | None:
        engine = self._engines[symbol]
        plan = engine.snapshot.execution_plan
        if plan is not None and plan.adaptive_exit_policy != "none":
            return adaptive_exit_action(
                symbol=symbol,
                snapshot=engine.snapshot,
                book=engine.latest_book,
                observed_ms=observed_ms,
                entry_price=entry_prices.get(symbol),
                market_bars=market_bars.get(symbol, ()),
                evaluations=evaluations,
                journal=self._telemetry.adaptive_exit_journal,
                degraded=self._adaptive_degraded,
            )
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
            exit_reason=_text(decision.get("exit_reason"), "exit_reason"),
        )

    def _retention_bound(self, symbol: str) -> bool:
        plan = self._engines[symbol].snapshot.execution_plan
        return plan is not None and plan.adaptive_exit_policy == RETENTION_EXIT_POLICY

    def _adaptive_degraded(self, *, source: str, reason: str) -> None:
        self._cycle_degraded = True
        self._telemetry.emit_poll_degraded(source=source, reason=reason)

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
        if plan.profit_lock_policy == "none":
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
        policy_bars = self._policy_bars(
            plan, symbol, opened_at_ms, observed_ms, market_bars
        )
        if policy_bars is None:
            return None
        state = self._policy_state(plan, side, entry, opened_at_ms, bars, policy_bars)
        if state.trigger is None:
            return None
        activation_mode = (
            state.activation_mode
            if isinstance(state, DelayedComponentFloorResult)
            else None
        )
        payload = _decision_payload(
            plan,
            provider,
            symbol,
            side,
            entry_oid,
            entry,
            state.trigger,
            activation_mode,
        )
        self._telemetry.emit_profit_lock_decision(payload)
        return payload

    def _policy_state(
        self,
        plan: BoundExecutionPlan,
        side: str,
        entry_price: float,
        opened_at_ms: int,
        lifecycle_bars: tuple[CohortMarketBar, ...],
        market_bars: tuple[CohortMarketBar, ...],
    ) -> ProfitLockPathState | DelayedComponentFloorResult:
        """Evaluate the exact bound fixed-bps or BTC Hulk lock policy."""
        if plan.profit_lock_policy == "completed_bar_trailing":
            return evaluate_profit_lock_path(
                _policy(plan), side, lifecycle_bars, entry_price
            )
        if plan.profit_lock_policy not in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
            raise MultiAssetLiveRunnerError("unsupported bound profit-lock policy")
        policy = delayed_component_policy(plan.profit_lock_policy)
        first = opened_at_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
        observations = build_btc_hulk_component_floor_observations(
            market_bars, lifecycle_start_ms=first
        )
        protective_stop = plan.stop_price(entry_price=entry_price, side=side)
        return evaluate_delayed_component_floor(
            policy,
            side=side,
            observations=observations,
            opened_at_ms=opened_at_ms,
            entry_price=entry_price,
            protective_stop_price=protective_stop,
        )

    def _policy_bars(
        self,
        plan: BoundExecutionPlan,
        symbol: str,
        opened_at_ms: int,
        observed_ms: int,
        bars: tuple[CohortMarketBar, ...],
    ) -> tuple[CohortMarketBar, ...] | None:
        """Anchor component warmup so restarts cannot shift indicator state."""
        if plan.profit_lock_policy not in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
            return bars
        policy = delayed_component_policy(plan.profit_lock_policy)
        first = opened_at_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
        seed = first - policy.warmup_ms
        last = (observed_ms - _MINUTE_MS) // _MINUTE_MS * _MINUTE_MS
        scoped = tuple(bar for bar in bars if seed <= bar.timestamp_ms <= last)
        expected = (last - seed) // _MINUTE_MS + 1
        valid = (
            len(scoped) == expected
            and scoped[0].timestamp_ms == seed
            and scoped[-1].timestamp_ms == last
            and all(bar.symbol == symbol for bar in scoped)
            and all(
                right.timestamp_ms - left.timestamp_ms == _MINUTE_MS
                for left, right in zip(scoped, scoped[1:], strict=False)
            )
        )
        if valid:
            return scoped
        reason = (
            f"{symbol} component floor missing anchored candles: "
            f"expected={expected} observed={len(scoped)}"
        )
        self._telemetry.emit_poll_degraded(
            source="profit_lock_component_candles", reason=reason
        )
        self._cycle_degraded = True
        return None

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
    activation_mode: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": f"{symbol}:{entry_oid}:profit_lock_exit",
        "lifecycle_id": f"{symbol}:{entry_oid}",
        "strategy_id": provider,
        "symbol": symbol,
        "side": side,
        "outcome": "exit",
        "exit_reason": _exit_reason(plan, activation_mode),
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
    if plan.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
        payload.update(
            {
                "profit_lock_contract": _policy_contract(plan),
                "component_exit_activation_mode": activation_mode,
                "target_policy": plan.target_policy,
                "target_r_multiple": plan.target_r_multiple,
            }
        )
    return payload


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
        "exit_reason": _exit_reason(
            plan,
            payload.get("component_exit_activation_mode"),
        ),
        "profit_lock_policy": plan.profit_lock_policy,
        "profit_lock_activation_bps": plan.profit_lock_activation_bps,
        "profit_lock_floor_bps": plan.profit_lock_floor_bps,
        "profit_lock_giveback_bps": plan.profit_lock_giveback_bps,
    }
    if plan.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
        expected.update(
            {
                "profit_lock_contract": _policy_contract(plan),
                "component_exit_activation_mode": payload.get(
                    "component_exit_activation_mode"
                ),
                "target_policy": plan.target_policy,
                "target_r_multiple": plan.target_r_multiple,
            }
        )
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


def _exit_reason(plan: BoundExecutionPlan, activation_mode: object = None) -> str:
    if plan.profit_lock_policy == BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id:
        return "btc_hulk_delayed_component_profit_floor"
    if plan.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
        if activation_mode == "profit_floor":
            return "btc_hulk_delayed_component_profit_floor"
        if activation_mode == "reversal_containment":
            return "btc_hulk_delayed_component_reversal_containment"
        raise MultiAssetLiveRunnerError("BTC delayed component exit lacks its mode")
    return "completed_bar_profit_lock"


def _policy_contract(plan: BoundExecutionPlan) -> dict[str, object] | None:
    if plan.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
        return component_floor_policy_payload(
            delayed_component_policy(plan.profit_lock_policy)
        )
    return None
