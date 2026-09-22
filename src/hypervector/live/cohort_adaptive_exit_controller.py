"""Lifecycle-bound adaptive observations persisted before reduce-only exits."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
import math

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_adaptive_exit_inputs import prepare_adaptive_inputs
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_adaptive_exit_policy import (
    ADAPTIVE_EXIT_POLICY, AdaptiveExitObservation, AdaptiveExitState, advance_adaptive_exit,
)
from hypervector.live.hyperliquid_protocol import SolBookSnapshot
from hypervector.live.cohort_exit_continuation_shadow import continuation_shadow
from hypervector.live.multi_asset_live_runner_support import entry_provider_strategy_id
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


def adaptive_exit_action(
    *, symbol: str, snapshot: SolLiveSnapshot, book: SolBookSnapshot | None,
    observed_ms: int, entry_price: float | None, market_bars: tuple[CohortMarketBar, ...],
    evaluations: tuple[ProviderEvaluation, ...], journal: AdaptiveExitJournal,
    degraded: Callable[..., None],
) -> RoutingAction | None:
    """Return an exact persisted exit; unknown data cannot fabricate protection."""
    plan = snapshot.execution_plan
    if snapshot.state is not SolLiveState.OPEN or plan is None or plan.adaptive_exit_policy == "none":
        return None
    if plan.adaptive_exit_policy != ADAPTIVE_EXIT_POLICY:
        raise ValueError("unsupported bound adaptive exit policy")
    identity = _identity(symbol, snapshot, entry_price)
    recorded = journal.recorded(str(identity["lifecycle_id"]))
    state = _recover(recorded, identity, observed_ms)
    inputs = prepare_adaptive_inputs(
        symbol=symbol, side=str(identity["side"]), entry_price=float(identity["entry_price"]),
        opened_ms=int(identity["opened_at_ms"]), observed_ms=observed_ms,
        book=book, bars=market_bars, evaluations=evaluations,
    )
    if state.exit_reason is not None and inputs.price is not None:
        return _action(identity, state, inputs.price)
    atr = inputs.atr_bps
    if inputs.price is None or atr is None:
        degraded(source="adaptive_exit_inputs", reason=f"{symbol}: missing fresh price or contiguous ATR history")
        if not state.armed or inputs.price is None or recorded is None:
            return None
        atr = _number(recorded["atr_bps"])
    sign = 1 if identity["side"] == "long" else -1
    observation = AdaptiveExitObservation(observed_ms,
        sign * (inputs.price / float(identity["entry_price"]) - 1) * 10_000,
        atr, inputs.friction_bps, inputs.alignment, inputs.book_ms, inputs.signed_pressure)
    updated = advance_adaptive_exit(state, observation)
    if updated == state:
        return None
    payload = {**identity, **asdict(inputs), "observed_ms": observed_ms, "atr_bps": atr,
               "reference_price": inputs.price, "pnl_bps": observation.pnl_bps,
               "state": asdict(updated), "cost_basis": "20bps_round_trip_plus_spread_excludes_funding"}
    payload["continuation_ml"] = continuation_shadow(symbol, str(identity["side"]), market_bars, observed_ms)
    journal.append(payload)
    return _action(identity, updated, inputs.price) if updated.exit_reason is not None else None


def _identity(symbol: str, snapshot: SolLiveSnapshot, entry_price: float | None) -> dict[str, object]:
    if snapshot.entry_oid is None or snapshot.opened_at_ms is None or snapshot.position_size_signed == 0:
        raise ValueError("adaptive exit requires exact open lifecycle identity")
    if snapshot.execution_plan is None or entry_price is None or _number(entry_price) <= 0:
        raise ValueError("adaptive exit requires bound plan and positive venue entry price")
    return {"lifecycle_id": f"{symbol}:{snapshot.entry_oid}:{snapshot.opened_at_ms}",
            "symbol": symbol, "entry_oid": snapshot.entry_oid, "opened_at_ms": snapshot.opened_at_ms,
            "entry_price": entry_price, "side": "long" if snapshot.position_size_signed > 0 else "short",
            "execution_plan": snapshot.execution_plan.as_payload(),
            "strategy_id": entry_provider_strategy_id(snapshot.execution_plan.strategy_id)}


def _recover(recorded: Mapping[str, object] | None, identity: Mapping[str, object],
             observed_ms: int) -> AdaptiveExitState:
    if recorded is None:
        return AdaptiveExitState()
    if any(recorded.get(key) != value for key, value in identity.items()):
        raise ValueError("adaptive exit recovery identity conflicts with venue lifecycle")
    raw = recorded.get("state")
    if not isinstance(raw, Mapping):
        raise ValueError("adaptive exit recovery lacks state")
    stamp, count = _integer(raw.get("observed_ms")), _integer(raw.get("book_count"))
    armed, reason = raw.get("armed"), raw.get("exit_reason")
    peak, floor = _number(raw.get("peak_bps")), raw.get("floor_bps")
    book_ms = raw.get("book_ms")
    if (stamp != recorded.get("observed_ms") or not int(identity["opened_at_ms"]) <= stamp <= observed_ms
            or not 0 <= count <= 3 or not isinstance(armed, bool) or peak < 0
            or reason not in {None, "adaptive_profit_floor"}):
        raise ValueError("invalid adaptive recovery state boundary")
    if armed != (floor is not None) or (reason is not None and not armed):
        raise ValueError("adaptive recovery floor contradicts activation")
    return AdaptiveExitState(stamp, peak, armed, None if floor is None else _number(floor),
                             None if book_ms is None else _integer(book_ms), count, reason)


def _action(identity: Mapping[str, object], state: AdaptiveExitState, price: float) -> RoutingAction:
    return RoutingAction("close", str(identity["strategy_id"]), str(identity["symbol"]),
                         str(identity["side"]), state.observed_ms, price,
                         exit_reason=state.exit_reason)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("adaptive recovery value must be finite numeric")
    return float(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("adaptive recovery timestamp/count must be nonnegative integer")
    return value
