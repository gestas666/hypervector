"""Fixed-entry HYPE take-profit sensitivity with frozen OOS isolation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_mature_profit_floor_sensitivity import (
    _completed_path,
    _fold_summary,
    _funding_bps,
    _number,
    _positive,
    _report_contract,
    _side,
    _summary,
    _timestamp,
    _validate_fold_count,
    _validate_market,
)

Record = Mapping[str, object]
TARGET_GRID_BPS = (40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0)
TARGET_EXIT_TAIL_SLIPPAGE_BPS = 5.0
_BPS_DENOMINATOR = 10_000.0


def entry_identity(trades: pd.DataFrame) -> str:
    """Hash the ordered fixed-entry cohort and reject duplicate lifecycles."""
    records = _trade_records(trades)
    identities = [_entry_record(row) for row in records]
    keys = [(row["side"], row["entry_time_utc"]) for row in identities]
    if len(set(keys)) != len(keys):
        raise ValueError("HYPE fixed-target cohort has duplicate entry identity")
    payload = json.dumps(identities, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_fixed_target_period(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    target_bps: float,
    config: HypeExitReplayConfig,
    fold_count: int,
    target_exit_slippage_bps: float,
) -> dict[str, object]:
    """Evaluate one target while preserving the exact native entry cohort."""
    _validate_market(market)
    _validate_fold_count(fold_count)
    target = _positive(target_bps, "target_bps")
    slippage = _target_slippage(target_exit_slippage_bps, config)
    identity = entry_identity(trades)
    outcomes = tuple(
        _evaluate_trade(market, row, target, slippage, config)
        for row in _trade_records(trades)
    )
    native = _target_summary(outcomes, "actual_net_return_bps", count_triggers=False)
    challenger = _target_summary(
        outcomes, "estimated_net_return_bps", count_triggers=True
    )
    return {
        "target_bps": target,
        "target_exit_slippage_bps": slippage,
        "fixed_entry_cohort": True,
        "entry_identity_sha256": identity,
        "native": native,
        "challenger": challenger,
        "challenger_minus_native_net_bps": (
            float(challenger["net_return_bps"]) - float(native["net_return_bps"])
        ),
        "folds": _fold_summary(market.index, outcomes, fold_count),
        "outcomes": list(outcomes),
    }


def build_fixed_target_report(
    development_market: pd.DataFrame,
    development_trades: pd.DataFrame,
    confirmation_periods: tuple[tuple[pd.DataFrame, pd.DataFrame], ...],
    *,
    target_grid_bps: Sequence[float] = TARGET_GRID_BPS,
    config: HypeExitReplayConfig,
    development_fold_count: int,
    target_exit_tail_slippage_bps: float = TARGET_EXIT_TAIL_SLIPPAGE_BPS,
) -> dict[str, object]:
    """Select on development and evaluate only the frozen target later."""
    grid = _target_grid(target_grid_bps)
    trials = tuple(
        _candidate(
            development_market,
            development_trades,
            target,
            config,
            development_fold_count,
            target_exit_tail_slippage_bps,
        )
        for target in grid
    )
    selection = _select_development(trials)
    selected = float(selection["selected_target_bps"])
    confirmation = _confirmation(
        confirmation_periods,
        selected,
        config,
        target_exit_tail_slippage_bps,
    )
    return {
        "schema_version": 1,
        "mode": "hype_aligned_fixed_target_sensitivity_v1",
        "contract": _report_contract(),
        "execution_contract": _execution_contract(config),
        "target_grid_bps": list(grid),
        "development_grid": list(trials),
        "selection": selection,
        "later_confirmation": confirmation,
        "disposition": _disposition(trials, selection, confirmation),
        "limitations": _limitations(),
    }


def _candidate(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    target: float,
    config: HypeExitReplayConfig,
    fold_count: int,
    tail_slippage: float,
) -> dict[str, object]:
    nominal = evaluate_fixed_target_period(
        market,
        trades,
        target_bps=target,
        config=config,
        fold_count=fold_count,
        target_exit_slippage_bps=config.slippage_bps_per_side,
    )
    tail = evaluate_fixed_target_period(
        market,
        trades,
        target_bps=target,
        config=config,
        fold_count=fold_count,
        target_exit_slippage_bps=tail_slippage,
    )
    if nominal["entry_identity_sha256"] != tail["entry_identity_sha256"]:
        raise RuntimeError("HYPE fixed-target scenario entry identities diverged")
    return {"target_bps": target, "nominal": nominal, "target_exit_tail": tail}


def _evaluate_trade(
    market: pd.DataFrame,
    trade: Record,
    target_bps: float,
    target_slippage_bps: float,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    side = _side(trade.get("side"))
    entry = _timestamp(trade.get("entry_time_utc"), "entry")
    exit_time = _timestamp(trade.get("exit_time_utc"), "exit")
    if exit_time <= entry:
        raise ValueError("HYPE fixed-target exit must follow entry")
    entry_price = _positive(trade.get("entry_price"), "entry price")
    native = _number(trade.get("net_return_bps"), "native net return")
    target = _target_price(entry_price, side, target_bps)
    hit = _first_target_hit(market, entry, exit_time, side, target)
    if hit is None:
        return _preserved_outcome(trade, side, entry, native)
    challenger = _target_net(
        market, side, entry, hit, entry_price, target, target_slippage_bps, config
    )
    return _triggered_outcome(trade, side, entry, hit, target, native, challenger)


def _first_target_hit(
    market: pd.DataFrame,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    side: str,
    target: float,
) -> pd.Timestamp | None:
    for candle in _completed_path(market, entry, exit_time):
        crossed = candle.high >= target if side == "long" else candle.low <= target
        if crossed:
            return pd.to_datetime(candle.timestamp_ms, unit="ms", utc=True)
    return None


def _target_net(
    market: pd.DataFrame,
    side: str,
    entry: pd.Timestamp,
    hit: pd.Timestamp,
    entry_price: float,
    target: float,
    slippage_bps: float,
    config: HypeExitReplayConfig,
) -> float:
    fraction = slippage_bps / _BPS_DENOMINATOR
    exit_price = target * (1.0 - fraction if side == "long" else 1.0 + fraction)
    sign = 1.0 if side == "long" else -1.0
    gross = sign * (exit_price / entry_price - 1.0) * _BPS_DENOMINATOR
    fees = config.fee_bps_per_side * (1.0 + exit_price / entry_price)
    return gross - fees + _funding_bps(market, side, entry, hit, entry_price)


def _preserved_outcome(
    trade: Record, side: str, entry: pd.Timestamp, native: float
) -> dict[str, object]:
    reason = str(trade.get("exit_reason"))
    return {
        "entry_timestamp_utc": entry.isoformat(),
        "side": side,
        "status": "native_exit_preserved",
        "native_exit_reason": reason,
        "challenger_exit_reason": reason,
        "target_timestamp_utc": None,
        "target_reference_price": None,
        "actual_net_return_bps": native,
        "estimated_net_return_bps": native,
        "native_net_return_bps": native,
        "challenger_net_return_bps": native,
        "challenger_minus_native_net_bps": 0.0,
    }


def _triggered_outcome(
    trade: Record,
    side: str,
    entry: pd.Timestamp,
    hit: pd.Timestamp,
    target: float,
    native: float,
    challenger: float,
) -> dict[str, object]:
    return {
        "entry_timestamp_utc": entry.isoformat(),
        "side": side,
        "status": "target_triggered",
        "native_exit_reason": str(trade.get("exit_reason")),
        "challenger_exit_reason": "fixed_target",
        "target_timestamp_utc": hit.isoformat(),
        "target_reference_price": target,
        "actual_net_return_bps": native,
        "estimated_net_return_bps": challenger,
        "native_net_return_bps": native,
        "challenger_net_return_bps": challenger,
        "challenger_minus_native_net_bps": challenger - native,
    }


def _confirmation(
    periods: tuple[tuple[pd.DataFrame, pd.DataFrame], ...],
    target: float,
    config: HypeExitReplayConfig,
    tail_slippage: float,
) -> dict[str, object]:
    if not periods:
        raise ValueError("HYPE fixed-target confirmation requires a period")
    nominal = tuple(
        evaluate_fixed_target_period(
            market,
            trades,
            target_bps=target,
            config=config,
            fold_count=1,
            target_exit_slippage_bps=config.slippage_bps_per_side,
        )
        for market, trades in periods
    )
    tail = tuple(
        evaluate_fixed_target_period(
            market,
            trades,
            target_bps=target,
            config=config,
            fold_count=1,
            target_exit_slippage_bps=tail_slippage,
        )
        for market, trades in periods
    )
    return {
        "selected_target_bps": target,
        "used_for_selection": False,
        "nominal": _combine_periods(nominal),
        "target_exit_tail": _combine_periods(tail),
    }


def _combine_periods(periods: tuple[Record, ...]) -> dict[str, object]:
    outcomes = tuple(
        outcome
        for period in periods
        for outcome in _outcome_records(period.get("outcomes"))
    )
    native = _target_summary(outcomes, "actual_net_return_bps", count_triggers=False)
    challenger = _target_summary(
        outcomes, "estimated_net_return_bps", count_triggers=True
    )
    return {
        "periods": len(periods),
        "native": native,
        "challenger": challenger,
        "challenger_minus_native_net_bps": (
            float(challenger["net_return_bps"]) - float(native["net_return_bps"])
        ),
        "outcomes": list(outcomes),
    }


def _select_development(trials: tuple[Record, ...]) -> dict[str, object]:
    selected = max(trials, key=_selection_key)
    nominal = _object(selected.get("nominal"), "nominal trial")
    return {
        "rule": (
            "tail_net_and_without_largest_positive,tail_net_positive,"
            "tail_without_largest_positive,tail_positive_folds,"
            "worst_tail_fold,tail_without_largest,tail_net,lower_target"
        ),
        "selected_target_bps": float(selected["target_bps"]),
        "development_entry_identity_sha256": str(nominal["entry_identity_sha256"]),
        "later_confirmation_used": False,
    }


def _target_summary(
    outcomes: tuple[Record, ...], field: str, *, count_triggers: bool
) -> dict[str, object]:
    summary = _summary(outcomes, field, count_triggers=False)
    if count_triggers:
        summary["triggered_lifecycles"] = sum(
            row.get("status") == "target_triggered" for row in outcomes
        )
    return summary


def _selection_key(row: Record) -> tuple[float, ...]:
    period = _object(row.get("target_exit_tail"), "tail trial")
    folds = _object(period.get("folds"), "tail folds")
    summary = _object(period.get("challenger"), "tail challenger")
    values = tuple(float(value) for value in folds["challenger_net_bps"])
    net = float(summary["net_return_bps"])
    ex_largest = float(summary["without_largest_winner_net_bps"])
    return (
        float(net > 0.0 and ex_largest > 0.0),
        float(net > 0.0),
        float(ex_largest > 0.0),
        float(folds["challenger_positive_folds"]),
        min(values),
        ex_largest,
        net,
        -float(row["target_bps"]),
    )


def _disposition(
    trials: tuple[Record, ...],
    selection: Record,
    confirmation: Record,
) -> str:
    selected_target = float(selection["selected_target_bps"])
    selected = next(
        row for row in trials if float(row["target_bps"]) == selected_target
    )
    tail = _object(selected.get("target_exit_tail"), "selected tail")
    challenger = _object(tail.get("challenger"), "selected challenger")
    native = _object(tail.get("native"), "selected native")
    if float(challenger["net_return_bps"]) <= float(native["net_return_bps"]) or float(
        challenger["without_largest_winner_net_bps"]
    ) <= float(native["without_largest_winner_net_bps"]):
        return "retain_native_exit_target_not_robust_in_development"
    later = _object(confirmation.get("target_exit_tail"), "confirmation tail")
    later_challenger = _object(later.get("challenger"), "confirmation challenger")
    if int(later_challenger["triggered_lifecycles"]) == 0:
        return "defer_until_independent_target_trigger"
    return "report_only_target_requires_human_review"


def _target_grid(values: Sequence[float]) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not values:
        raise ValueError("HYPE fixed-target grid must be non-empty")
    parsed = tuple(_positive(value, "target_bps") for value in values)
    if len(set(parsed)) != len(parsed):
        raise ValueError("HYPE fixed-target grid contains duplicates")
    return parsed


def _target_slippage(value: float, config: HypeExitReplayConfig) -> float:
    parsed = _number(value, "target exit slippage")
    if parsed < config.slippage_bps_per_side:
        raise ValueError("target exit slippage cannot be below nominal slippage")
    return parsed


def _target_price(entry_price: float, side: str, target_bps: float) -> float:
    direction = 1.0 if side == "long" else -1.0
    return entry_price * (1.0 + direction * target_bps / _BPS_DENOMINATOR)


def _trade_records(trades: pd.DataFrame) -> tuple[Record, ...]:
    required = {
        "side",
        "entry_time_utc",
        "exit_time_utc",
        "entry_price",
        "net_return_bps",
        "exit_reason",
    }
    if required - set(trades.columns) or trades.empty:
        raise ValueError("HYPE fixed-target lifecycle sidecar is incomplete")
    return tuple(trades.to_dict(orient="records"))


def _entry_record(row: Record) -> dict[str, object]:
    return {
        "side": _side(row.get("side")),
        "entry_time_utc": _timestamp(row.get("entry_time_utc"), "entry").isoformat(),
        "entry_price": _positive(row.get("entry_price"), "entry price"),
        "native_exit_time_utc": _timestamp(
            row.get("exit_time_utc"), "exit"
        ).isoformat(),
        "native_exit_reason": str(row.get("exit_reason")),
    }


def _outcome_records(value: object) -> tuple[Record, ...]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError("HYPE fixed-target outcomes must be objects")
    return tuple(value)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"HYPE fixed-target {label} must be an object")
    return value


def _execution_contract(config: HypeExitReplayConfig) -> dict[str, object]:
    return {
        "stop_bps": config.stop_bps,
        "maximum_hold_minutes": config.maximum_hold_minutes,
        "maximum_hold_policy": config.maximum_hold_policy,
        "hard_maximum_hold_minutes": config.hard_maximum_hold_minutes,
        "fee_bps_per_side": config.fee_bps_per_side,
        "nominal_slippage_bps_per_side": config.slippage_bps_per_side,
        "exit_on_opposite_signal": config.exit_on_opposite_signal,
    }


def _limitations() -> list[str]:
    return [
        "the target grid was declared after inspecting development MFE distribution",
        "fixed-entry sensitivity does not model changed re-entry availability",
        "the native exit wins target ambiguity on its own exit bar",
        "one-minute OHLC cannot prove intrabar event order or private IOC fills",
        "target-exit tail slippage is not a full-strategy stress replay",
        "later confirmation was already opened and contains one aligned lifecycle",
        "no live strategy, exit, sizing, routing, or promotion authority is granted",
    ]
