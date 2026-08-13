"""Report-only causal trail challengers after a soft maximum-hold boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Protocol

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
_GIVEBACK_BPS = (20.0, 30.0, 40.0)
_LATEST_LIMIT = 50
_MINUTE_MS = 60_000


class CandleLike(Protocol):
    """Completed one-minute candle fields required by the challenger."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class _Economics:
    entry_timestamp_ms: int
    entry_price: float
    size: float
    entry_fee_usd: float
    actual_exit_price: float
    actual_exit_fee_rate: float
    actual_net_pnl_usd: float
    soft_net_pnl_usd: float
    soft_reference_price: float
    fill_reference_ratio: float


@dataclass(frozen=True)
class _Trigger:
    timestamp_ms: int
    reference_price: float
    trail_price: float
    best_completed_price: float


def build_post_soft_trail_challenger(
    outcomes: Sequence[Record],
    reflected_trades: Sequence[Record],
    candles: Mapping[str, Mapping[int, CandleLike]],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    """Compare frozen post-soft giveback trails with actual and soft exits."""
    trades = _trade_index(reflected_trades)
    results = [
        _lifecycle_result(outcome, _required_trade(outcome, trades), candles, funding)
        for outcome in outcomes
    ]
    results.sort(
        key=lambda row: nonnegative_int(row["actual_exit_timestamp_ms"], "exit")
    )
    return {
        "schema_version": 1,
        "mode": "cohort_post_soft_trail_challenger_v1",
        "contract": _contract(),
        "policies_giveback_bps": list(_GIVEBACK_BPS),
        "summary_by_giveback_bps": _summaries(results),
        "latest_results": results[-_LATEST_LIMIT:],
        "limitations": _limitations(),
    }


def build_open_post_soft_trail_status(
    candles: Mapping[int, CandleLike],
    side: str,
    *,
    soft_deadline_ms: int,
    as_of_ms: int,
) -> dict[str, object]:
    """Project frozen causal trail state for one still-open extension."""
    direction = text(side, "open post-soft side")
    if direction not in {"long", "short"}:
        raise ValueError("open post-soft side must be long or short")
    boundary = nonnegative_int(soft_deadline_ms, "open post-soft deadline")
    observed = nonnegative_int(as_of_ms, "open post-soft observation")
    if observed < boundary:
        return _open_trail_report(
            "pending_soft_deadline", boundary, observed, None, (), direction
        )
    completed_before = tuple(
        candle
        for timestamp, candle in sorted(candles.items())
        if _validated_timestamp(timestamp, candle) + _MINUTE_MS <= boundary
    )
    if not completed_before:
        return _open_trail_report(
            "unavailable_boundary_close", boundary, observed, None, (), direction
        )
    baseline = completed_before[-1]
    bars = _completed_extension_bars(candles, boundary, observed)
    status = "observed" if bars else "awaiting_completed_bar"
    return _open_trail_report(status, boundary, observed, baseline, bars, direction)


def _validated_timestamp(timestamp_ms: int, candle: CandleLike) -> int:
    if candle.timestamp_ms != timestamp_ms:
        raise ValueError("post-soft candle key and timestamp disagree")
    _validate_candle(candle)
    return timestamp_ms


def _open_trail_report(
    status: str,
    boundary_ms: int,
    observed_ms: int,
    baseline: CandleLike | None,
    bars: Sequence[CandleLike],
    side: str,
) -> dict[str, object]:
    baseline_price = None if baseline is None else baseline.close
    policies = {
        _policy_key(giveback): _open_policy_result(
            status, side, giveback, bars, baseline_price
        )
        for giveback in _GIVEBACK_BPS
    }
    return {
        "schema_version": 1,
        "mode": "cohort_open_post_soft_trail_challenger_v1",
        "contract": _contract(),
        "status": status,
        "soft_deadline_timestamp_ms": boundary_ms,
        "as_of_timestamp_ms": observed_ms,
        "baseline_timestamp_ms": None if baseline is None else baseline.timestamp_ms,
        "baseline_price": baseline_price,
        "completed_post_soft_bars": len(bars),
        "policies": policies,
    }


def _open_policy_result(
    status: str,
    side: str,
    giveback_bps: float,
    bars: Sequence[CandleLike],
    baseline_price: float | None,
) -> dict[str, object]:
    if baseline_price is None or not bars:
        return _open_unavailable_policy(giveback_bps, status)
    trigger = _find_trigger(side, giveback_bps, bars, baseline_price)
    if trigger is not None:
        return {
            "giveback_bps": giveback_bps,
            "status": "triggered",
            "trigger_timestamp_ms": trigger.timestamp_ms,
            "trigger_reference_price": trigger.reference_price,
            "best_completed_price_before_trigger": trigger.best_completed_price,
            "active_trail_price": trigger.trail_price,
        }
    best = baseline_price
    for candle in bars:
        best = max(best, candle.high) if side == "long" else min(best, candle.low)
    return {
        "giveback_bps": giveback_bps,
        "status": "armed_not_triggered",
        "trigger_timestamp_ms": None,
        "trigger_reference_price": None,
        "best_completed_price": best,
        "active_trail_price": _trail_price(side, best, giveback_bps),
    }


def _open_unavailable_policy(giveback_bps: float, status: str) -> dict[str, object]:
    return {
        "giveback_bps": giveback_bps,
        "status": status,
        "trigger_timestamp_ms": None,
        "trigger_reference_price": None,
        "best_completed_price": None,
        "active_trail_price": None,
    }


def _trade_index(trades: Sequence[Record]) -> dict[str, Record]:
    output: dict[str, Record] = {}
    for trade in trades:
        lifecycle = text(trade.get("lifecycle_id"), "trade lifecycle")
        if lifecycle in output:
            raise ValueError(f"duplicate reflected lifecycle: {lifecycle}")
        output[lifecycle] = trade
    return output


def _required_trade(outcome: Record, trades: Mapping[str, Record]) -> Record:
    lifecycle = text(outcome.get("lifecycle_id"), "outcome lifecycle")
    trade = trades.get(lifecycle)
    if trade is None:
        raise ValueError(f"post-soft outcome lacks reflected trade: {lifecycle}")
    return trade


def _lifecycle_result(
    outcome: Record,
    trade: Record,
    candles: Mapping[str, Mapping[int, CandleLike]],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    lifecycle, symbol, strategy, side = _validated_identity(outcome, trade)
    soft_ms = nonnegative_int(
        outcome.get("soft_deadline_timestamp_ms"), "soft deadline"
    )
    exit_ms = nonnegative_int(outcome.get("actual_exit_timestamp_ms"), "actual exit")
    if exit_ms <= soft_ms:
        raise ValueError(f"{lifecycle} is not a resolved extension")
    economics = _economics(outcome, trade, exit_ms)
    bars = _completed_extension_bars(candles.get(symbol, {}), soft_ms, exit_ms)
    policies = {
        _policy_key(giveback): _policy_result(
            side, giveback, bars, economics, funding.get(symbol, {})
        )
        for giveback in _GIVEBACK_BPS
    }
    return {
        "lifecycle_id": lifecycle,
        "symbol": symbol,
        "strategy_id": strategy,
        "side": side,
        "soft_deadline_timestamp_ms": soft_ms,
        "actual_exit_timestamp_ms": exit_ms,
        "completed_post_soft_bars": len(bars),
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_soft_net_pnl_usd": economics.soft_net_pnl_usd,
        "policies": policies,
    }


def _validated_identity(outcome: Record, trade: Record) -> tuple[str, str, str, str]:
    lifecycle = text(outcome.get("lifecycle_id"), "outcome lifecycle")
    symbol = text(outcome.get("symbol"), "outcome symbol")
    strategy = text(outcome.get("strategy_id"), "outcome strategy")
    side = text(outcome.get("side"), "outcome side")
    expected = (
        text(trade.get("lifecycle_id"), "trade lifecycle"),
        text(trade.get("symbol"), "trade symbol"),
        text(trade.get("strategy_id"), "trade strategy"),
        text(trade.get("side"), "trade side"),
    )
    if expected != (lifecycle, symbol, strategy, side):
        raise ValueError(f"{lifecycle} post-soft identity is inconsistent")
    if side not in {"long", "short"}:
        raise ValueError(f"{lifecycle} side must be long or short")
    return lifecycle, symbol, strategy, side


def _economics(outcome: Record, trade: Record, exit_ms: int) -> _Economics:
    entry = mapping(trade.get("entry"), "post-soft trade entry")
    exit_leg = mapping(trade.get("exit"), "post-soft trade exit")
    if nonnegative_int(exit_leg.get("venue_timestamp_ms"), "trade exit") != exit_ms:
        raise ValueError("post-soft actual exit timestamps are inconsistent")
    entry_price = _positive_number(entry.get("price"), "entry price")
    size = _positive_number(entry.get("size"), "entry size")
    actual_exit_price = _positive_number(exit_leg.get("price"), "actual exit price")
    actual_exit_fee = _nonnegative_number(
        outcome.get("actual_exit_fee_usd"), "actual exit fee"
    )
    soft_reference = _positive_number(
        outcome.get("soft_reference_price"), "soft reference"
    )
    estimated_soft_exit = _positive_number(
        outcome.get("estimated_soft_exit_price"), "estimated soft exit"
    )
    return _Economics(
        nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp"),
        entry_price,
        size,
        _nonnegative_number(outcome.get("entry_fee_usd"), "entry fee"),
        actual_exit_price,
        actual_exit_fee / (actual_exit_price * size),
        number(outcome.get("actual_net_pnl_usd"), "actual net PnL"),
        number(outcome.get("estimated_soft_net_pnl_usd"), "soft net PnL"),
        soft_reference,
        estimated_soft_exit / soft_reference,
    )


def _completed_extension_bars(
    values: Mapping[int, CandleLike], soft_ms: int, exit_ms: int
) -> tuple[CandleLike, ...]:
    bars: list[CandleLike] = []
    for timestamp, candle in sorted(values.items()):
        if candle.timestamp_ms != timestamp:
            raise ValueError("post-soft candle key and timestamp disagree")
        _validate_candle(candle)
        if timestamp >= soft_ms and timestamp + _MINUTE_MS <= exit_ms:
            bars.append(candle)
    return tuple(bars)


def _validate_candle(candle: CandleLike) -> None:
    prices = (candle.open, candle.high, candle.low, candle.close)
    if any(not math.isfinite(value) or value <= 0.0 for value in prices):
        raise ValueError("post-soft candle prices must be finite and positive")
    if candle.high < max(candle.open, candle.low, candle.close):
        raise ValueError("post-soft candle high is inconsistent")
    if candle.low > min(candle.open, candle.high, candle.close):
        raise ValueError("post-soft candle low is inconsistent")


def _policy_result(
    side: str,
    giveback_bps: float,
    bars: Sequence[CandleLike],
    economics: _Economics,
    funding: Mapping[int, float],
) -> dict[str, object]:
    trigger = _find_trigger(side, giveback_bps, bars, economics.soft_reference_price)
    if trigger is None:
        return _untriggered_result(giveback_bps, economics)
    estimated_exit = trigger.reference_price * economics.fill_reference_ratio
    net = _trigger_net(side, estimated_exit, trigger.timestamp_ms, economics, funding)
    return {
        "giveback_bps": giveback_bps,
        "status": "triggered",
        "trigger_timestamp_ms": trigger.timestamp_ms,
        "trigger_reference_price": trigger.reference_price,
        "trail_price_before_trigger": trigger.trail_price,
        "best_completed_price_before_trigger": trigger.best_completed_price,
        "estimated_exit_price": estimated_exit,
        "estimated_net_pnl_usd": net,
        "trail_minus_actual_net_usd": net - economics.actual_net_pnl_usd,
        "trail_minus_soft_net_usd": net - economics.soft_net_pnl_usd,
    }


def _find_trigger(
    side: str,
    giveback_bps: float,
    bars: Sequence[CandleLike],
    baseline: float,
) -> _Trigger | None:
    best = baseline
    trail = _trail_price(side, best, giveback_bps)
    for candle in bars:
        crossed = candle.low <= trail if side == "long" else candle.high >= trail
        if crossed:
            reference = (
                min(candle.open, trail) if side == "long" else max(candle.open, trail)
            )
            return _Trigger(candle.timestamp_ms, reference, trail, best)
        best = max(best, candle.high) if side == "long" else min(best, candle.low)
        trail = _trail_price(side, best, giveback_bps)
    return None


def _trail_price(side: str, best: float, giveback_bps: float) -> float:
    fraction = giveback_bps / 10_000.0
    return best * (1.0 - fraction if side == "long" else 1.0 + fraction)


def _trigger_net(
    side: str,
    exit_price: float,
    timestamp_ms: int,
    economics: _Economics,
    funding: Mapping[int, float],
) -> float:
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price - economics.entry_price) * economics.size
    exit_fee = exit_price * economics.size * economics.actual_exit_fee_rate
    funding_net = sum(
        delta
        for observed_ms, delta in funding.items()
        if economics.entry_timestamp_ms <= observed_ms <= timestamp_ms
    )
    return gross - economics.entry_fee_usd - exit_fee + funding_net


def _untriggered_result(
    giveback_bps: float, economics: _Economics
) -> dict[str, object]:
    return {
        "giveback_bps": giveback_bps,
        "status": "not_triggered_before_actual_exit",
        "trigger_timestamp_ms": None,
        "trigger_reference_price": None,
        "trail_price_before_trigger": None,
        "best_completed_price_before_trigger": None,
        "estimated_exit_price": economics.actual_exit_price,
        "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
        "trail_minus_actual_net_usd": 0.0,
        "trail_minus_soft_net_usd": economics.actual_net_pnl_usd
        - economics.soft_net_pnl_usd,
    }


def _summaries(results: Sequence[Record]) -> dict[str, object]:
    summaries: dict[str, object] = {}
    for giveback in _GIVEBACK_BPS:
        policies = [
            mapping(row["policies"], "policies")[_policy_key(giveback)]
            for row in results
        ]
        summaries[str(int(giveback))] = _policy_summary(policies)
    return summaries


def _policy_summary(values: Sequence[object]) -> dict[str, object]:
    policies = [mapping(value, "trail policy") for value in values]
    actual = sum(
        number(row.get("estimated_net_pnl_usd"), "estimated net")
        - number(row.get("trail_minus_actual_net_usd"), "trail actual delta")
        for row in policies
    )
    soft = sum(
        number(row.get("estimated_net_pnl_usd"), "estimated net")
        - number(row.get("trail_minus_soft_net_usd"), "trail soft delta")
        for row in policies
    )
    return {
        "eligible_extension_lifecycles": len(policies),
        "triggered": sum(row.get("status") == "triggered" for row in policies),
        "not_triggered": sum(
            row.get("status") == "not_triggered_before_actual_exit" for row in policies
        ),
        "estimated_net_pnl_usd": sum(
            number(row.get("estimated_net_pnl_usd"), "estimated net")
            for row in policies
        ),
        "actual_net_pnl_usd": actual,
        "estimated_soft_net_pnl_usd": soft,
        "trail_minus_actual_net_usd": sum(
            number(row.get("trail_minus_actual_net_usd"), "trail actual delta")
            for row in policies
        ),
        "trail_minus_soft_net_usd": sum(
            number(row.get("trail_minus_soft_net_usd"), "trail soft delta")
            for row in policies
        ),
    }


def _policy_key(giveback_bps: float) -> str:
    return f"{int(giveback_bps)}bps"


def _positive_number(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _nonnegative_number(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return parsed


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "trails use prior completed one-minute extrema and cannot resolve intrabar order paths",
        "gap-through triggers use the bar open as the reference rather than the stale stop level",
        "estimated fills reuse the actual exit fill/reference ratio and fee rate",
        "untriggered policies inherit the actual exit rather than estimating another fill",
        "small resolved samples are descriptive evidence and cannot establish an exit edge",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
