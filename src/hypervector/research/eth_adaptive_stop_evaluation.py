"""Equal-risk evidence and frozen gates for the ETH adaptive-stop challenger."""

from __future__ import annotations

from collections.abc import Mapping
from statistics import median

from hypervector.research.hype_breakout_exit_models import HypeExitTrade

_CONTROL_STOP_BPS = 60.0


def summarize_equal_risk(
    trades: tuple[HypeExitTrade, ...],
    *,
    control_stop_bps: float = _CONTROL_STOP_BPS,
) -> dict[str, object]:
    """Summarize trade economics after equal barrier-risk notional scaling."""
    widths = [_resolved_stop_bps(trade) for trade in trades]
    scaled = [
        trade.net_return_bps * control_stop_bps / width
        for trade, width in zip(trades, widths, strict=True)
    ]
    monthly: dict[str, float] = {}
    by_side: dict[str, dict[str, object]] = {}
    for side in ("long", "short"):
        indices = [
            position for position, trade in enumerate(trades) if trade.side == side
        ]
        by_side[side] = _return_summary([scaled[position] for position in indices])
    for trade, value in zip(trades, scaled, strict=True):
        month = trade.exit_time_utc[:7]
        monthly[month] = monthly.get(month, 0.0) + value
    reasons: dict[str, int] = {}
    for trade in trades:
        reasons[trade.exit_reason] = reasons.get(trade.exit_reason, 0) + 1
    return {
        **_return_summary(scaled),
        "equal_risk_net_return_bps": sum(scaled),
        "equal_risk_net_excluding_largest_winner_bps": _excluding_largest(scaled),
        "maximum_drawdown_bps": _maximum_drawdown(scaled),
        "monthly_net_bps": monthly,
        "by_side": by_side,
        "exit_reasons": reasons,
        "resolved_stop_bps": _width_summary(widths),
    }


def compare_equal_risk(
    control_trades: tuple[HypeExitTrade, ...],
    candidate_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    """Compare one partition using the preregistered equal-risk metrics."""
    control = summarize_equal_risk(control_trades)
    candidate = summarize_equal_risk(candidate_trades)
    monthly_delta = _monthly_delta(control, candidate)
    return {
        "control": control,
        "candidate": candidate,
        "delta": {
            "net_return_bps": _metric(candidate, "equal_risk_net_return_bps")
            - _metric(control, "equal_risk_net_return_bps"),
            "net_excluding_largest_winner_bps": _metric(
                candidate, "equal_risk_net_excluding_largest_winner_bps"
            )
            - _metric(control, "equal_risk_net_excluding_largest_winner_bps"),
            "monthly_fold_bps": monthly_delta,
            "worst_monthly_fold_bps": min(monthly_delta.values())
            if monthly_delta
            else None,
        },
    }


def evaluate_eth_promotion(
    partitions: Mapping[str, Mapping[str, object]],
    *,
    source_signal_parity: bool,
) -> dict[str, object]:
    """Evaluate every preregistered ETH promotion criterion without overrides."""
    construction = _partition(partitions, "construction")
    confirmation = _partition(partitions, "confirmation")
    audit = _partition(partitions, "opened_final_audit")
    criteria = {
        "exact_entry_signal_timestamp_parity": source_signal_parity,
        "positive_construction_equal_risk_net_delta": _delta(
            construction, "net_return_bps"
        )
        > 0.0,
        "positive_confirmation_equal_risk_net_delta": _delta(
            confirmation, "net_return_bps"
        )
        > 0.0,
        "positive_construction_ex_largest_delta": _delta(
            construction, "net_excluding_largest_winner_bps"
        )
        > 0.0,
        "positive_confirmation_ex_largest_delta": _delta(
            confirmation, "net_excluding_largest_winner_bps"
        )
        > 0.0,
        "nonnegative_worst_confirmation_monthly_delta": _optional_delta(
            confirmation, "worst_monthly_fold_bps"
        )
        >= 0.0,
        "confirmation_drawdown_not_worse": _candidate_metric(
            confirmation, "maximum_drawdown_bps"
        )
        <= _control_metric(confirmation, "maximum_drawdown_bps"),
        "confirmation_long_nonnegative": _side_net(confirmation, "long") >= 0.0,
        "confirmation_short_nonnegative": _side_net(confirmation, "short") >= 0.0,
        "opened_final_delta_not_contradictory": _delta(audit, "net_return_bps") >= 0.0,
    }
    passed = all(criteria.values())
    return {
        "passed": passed,
        "criteria": criteria,
        "decision": "eligible_for_live_implementation_review"
        if passed
        else "retain_v61_eth_control",
    }


def _resolved_stop_bps(trade: HypeExitTrade) -> float:
    signed = (
        trade.entry_price - trade.stop_price
        if trade.side == "long"
        else trade.stop_price - trade.entry_price
    )
    width = signed / trade.entry_price * 10_000.0
    if width <= 0.0:
        raise ValueError("ETH replay trade has a non-adverse stop")
    return width


def _return_summary(values: list[float]) -> dict[str, object]:
    return {
        "trades": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value <= 0.0 for value in values),
        "net_return_bps": sum(values),
    }


def _width_summary(widths: list[float]) -> dict[str, float | None]:
    return {
        "minimum": min(widths) if widths else None,
        "median": median(widths) if widths else None,
        "maximum": max(widths) if widths else None,
        "mean": sum(widths) / len(widths) if widths else None,
    }


def _excluding_largest(values: list[float]) -> float:
    return sum(values) - max((value for value in values if value > 0.0), default=0.0)


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _monthly_delta(
    control: Mapping[str, object], candidate: Mapping[str, object]
) -> dict[str, float]:
    control_months = _mapping(control, "monthly_net_bps")
    candidate_months = _mapping(candidate, "monthly_net_bps")
    months = sorted(set(control_months).union(candidate_months))
    return {
        month: float(candidate_months.get(month, 0.0))
        - float(control_months.get(month, 0.0))
        for month in months
    }


def _partition(
    partitions: Mapping[str, Mapping[str, object]], name: str
) -> Mapping[str, object]:
    if name not in partitions:
        raise ValueError(f"ETH evaluation partition is missing: {name}")
    return partitions[name]


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"ETH evaluation mapping is missing: {key}")
    return value


def _metric(source: Mapping[str, object], key: str) -> float:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"ETH evaluation metric is missing: {key}")
    return float(value)


def _delta(partition: Mapping[str, object], key: str) -> float:
    return _metric(_mapping(partition, "delta"), key)


def _optional_delta(partition: Mapping[str, object], key: str) -> float:
    value = _mapping(partition, "delta").get(key)
    return (
        float("-inf") if value is None else _metric(_mapping(partition, "delta"), key)
    )


def _candidate_metric(partition: Mapping[str, object], key: str) -> float:
    return _metric(_mapping(partition, "candidate"), key)


def _control_metric(partition: Mapping[str, object], key: str) -> float:
    return _metric(_mapping(partition, "control"), key)


def _side_net(partition: Mapping[str, object], side: str) -> float:
    candidate = _mapping(partition, "candidate")
    side_summary = _mapping(_mapping(candidate, "by_side"), side)
    return _metric(side_summary, "net_return_bps")
