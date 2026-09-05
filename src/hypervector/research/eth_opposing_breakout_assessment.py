"""Economic assessment for the fixed ETH opposing-breakout exit."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from hypervector.research.eth_opposing_breakout_exit import (
    EthOpposingBreakoutReplay,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade, HypeSide

_FOLD_COUNT = 5


def build_eth_opposing_breakout_segment(
    control: tuple[HypeExitTrade, ...],
    candidate: EthOpposingBreakoutReplay,
    delay_stress: EthOpposingBreakoutReplay,
    *,
    include_folds: bool,
) -> dict[str, object]:
    """Build one fixed-entry control, candidate, and delay comparison."""
    candidate_trades = candidate.report.trades
    delayed_trades = delay_stress.report.trades
    _require_entry_parity(control, candidate_trades)
    _require_entry_parity(control, delayed_trades)
    _require_trigger_reconciliation(candidate)
    _require_trigger_reconciliation(delay_stress)
    control_summary = _summary(control, "native")
    candidate_summary = _summary(candidate_trades, "candidate")
    delay_summary = _summary(delayed_trades, "delay")
    technical_status = _combined_technical_status(candidate, delay_stress)
    return {
        "technical_status": technical_status,
        "entry_parity": True,
        "triggered_lifecycles": len(candidate.triggers),
        "delay_triggered_lifecycles": len(delay_stress.triggers),
        "unavailable_direction_rows": list(candidate.unavailable_direction_rows),
        "delay_unavailable_direction_rows": list(
            delay_stress.unavailable_direction_rows
        ),
        "control": control_summary,
        "candidate": candidate_summary,
        "delay_stress": delay_summary,
        "delta_net_return_bps": _net(candidate_summary) - _net(control_summary),
        "delay_delta_net_return_bps": _net(delay_summary) - _net(control_summary),
        "chronological_folds": (
            _folds(control, candidate_trades) if include_folds else []
        ),
    }


def assess_eth_opposing_breakout(
    development: Mapping[str, object],
    opened_final: Mapping[str, object],
) -> dict[str, object]:
    """Apply every preregistered technical and economic success condition."""
    dev_control = _child(development, "control")
    dev_candidate = _child(development, "candidate")
    final_control = _child(opened_final, "control")
    final_candidate = _child(opened_final, "candidate")
    folds = development.get("chronological_folds")
    if not isinstance(folds, list):
        raise ValueError("ETH opposing-breakout development folds must be a list")
    conditions = {
        "technical_paths_resolved": (
            development.get("technical_status")
            == opened_final.get("technical_status")
            == "resolved"
        ),
        "development_net_and_pf_improve": _economics_improve(
            dev_control, dev_candidate
        ),
        "development_ex_largest_positive": _ex_largest_positive(dev_candidate),
        "development_drawdown_not_worse": _drawdown_not_worse(
            dev_control, dev_candidate
        ),
        "development_fold_breadth": _fold_breadth(folds) >= 3,
        "opened_final_net_and_pf_improve": _economics_improve(
            final_control, final_candidate
        ),
        "opened_final_ex_largest_positive": _ex_largest_positive(final_candidate),
        "opened_final_drawdown_not_worse": _drawdown_not_worse(
            final_control, final_candidate
        ),
        "opened_final_both_sides_positive": _both_sides_positive(final_candidate),
        "delay_stress_development": _delay_passes(development),
        "delay_stress_opened_final": _delay_passes(opened_final),
    }
    failed = [name for name, passed in conditions.items() if not passed]
    return {
        "status": (
            "eligible_for_future_report_only_observer"
            if not failed
            else "rejected_historical_candidate"
        ),
        "conditions": conditions,
        "failed_conditions": failed,
        "proposed_live_change": "none",
        "explicit_approval_requested": False,
        "confidence": "low_retrospective_fixed_hypothesis",
    }


def _summary(trades: tuple[HypeExitTrade, ...], adapter: str) -> dict[str, object]:
    returns = [trade.net_return_bps for trade in trades]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    reasons = Counter(trade.exit_reason for trade in trades)
    if adapter != "native" and "structural_reversal" in reasons:
        label = f"opposing_breakout_{adapter}_next_open"
        reasons[label] = reasons.pop("structural_reversal")
    return {
        "trades": len(trades),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "net_return_bps": sum(returns),
        "profit_factor": gains / losses if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(returns),
        "net_excluding_largest_winner_bps": (
            sum(returns) - max((value for value in returns if value > 0.0), default=0.0)
        ),
        "exit_reasons": dict(sorted(reasons.items())),
        "by_side": {
            side: _side_summary(tuple(trade for trade in trades if trade.side == side))
            for side in ("long", "short")
        },
    }


def _side_summary(trades: tuple[HypeExitTrade, ...]) -> dict[str, object]:
    returns = [trade.net_return_bps for trade in trades]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    return {
        "trades": len(trades),
        "net_return_bps": sum(returns),
        "profit_factor": gains / losses if losses else None,
        "net_excluding_largest_winner_bps": (
            sum(returns) - max((value for value in returns if value > 0.0), default=0.0)
        ),
    }


def _folds(
    control: tuple[HypeExitTrade, ...],
    candidate: tuple[HypeExitTrade, ...],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for index in range(_FOLD_COUNT):
        start = index * len(control) // _FOLD_COUNT
        end = (index + 1) * len(control) // _FOLD_COUNT
        control_summary = _summary(control[start:end], "native")
        candidate_summary = _summary(candidate[start:end], "candidate")
        output.append(
            {
                "fold": index + 1,
                "control": control_summary,
                "candidate": candidate_summary,
                "delta_net_return_bps": (
                    _net(candidate_summary) - _net(control_summary)
                ),
            }
        )
    return output


def _require_trigger_reconciliation(candidate: EthOpposingBreakoutReplay) -> None:
    exits = sum(
        trade.exit_reason == "structural_reversal" for trade in candidate.report.trades
    )
    if exits > len(candidate.triggers):
        raise ValueError("ETH opposing-breakout exits exceed causal triggers")


def _combined_technical_status(
    candidate: EthOpposingBreakoutReplay,
    delay: EthOpposingBreakoutReplay,
) -> str:
    if candidate.technical_status == delay.technical_status == "resolved":
        return "resolved"
    return f"baseline={candidate.technical_status};delay={delay.technical_status}"


def _require_entry_parity(
    control: tuple[HypeExitTrade, ...],
    candidate: tuple[HypeExitTrade, ...],
) -> None:
    if [_entry_identity(trade) for trade in control] != [
        _entry_identity(trade) for trade in candidate
    ]:
        raise ValueError("ETH opposing-breakout artifact entry cohort changed")


def _entry_identity(trade: HypeExitTrade) -> tuple[str, str, HypeSide]:
    return trade.signal_time_utc, trade.entry_time_utc, trade.side


def _economics_improve(
    control: Mapping[str, object], candidate: Mapping[str, object]
) -> bool:
    return _net(candidate) > _net(control) and _profit_factor(
        candidate
    ) > _profit_factor(control)


def _delay_passes(segment: Mapping[str, object]) -> bool:
    control = _child(segment, "control")
    delayed = _child(segment, "delay_stress")
    return (
        _net(delayed) > 0.0
        and _profit_factor(delayed) > 1.0
        and _net(delayed) > _net(control)
    )


def _drawdown_not_worse(
    control: Mapping[str, object], candidate: Mapping[str, object]
) -> bool:
    return _number(candidate, "maximum_drawdown_bps") <= _number(
        control, "maximum_drawdown_bps"
    )


def _ex_largest_positive(candidate: Mapping[str, object]) -> bool:
    return _number(candidate, "net_excluding_largest_winner_bps") > 0.0


def _both_sides_positive(candidate: Mapping[str, object]) -> bool:
    sides = _child(candidate, "by_side")
    return all(
        _number(_child(sides, side), "net_return_bps") > 0.0
        for side in ("long", "short")
    )


def _fold_breadth(folds: list[object]) -> int:
    passing = 0
    for raw in folds:
        if not isinstance(raw, Mapping):
            raise ValueError("ETH opposing-breakout fold must be an object")
        candidate = _child(raw, "candidate")
        if _net(candidate) > 0.0 and _number(raw, "delta_net_return_bps") > 0.0:
            passing += 1
    return passing


def _maximum_drawdown(returns: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _profit_factor(summary: Mapping[str, object]) -> float:
    value = summary.get("profit_factor")
    return (
        float("inf") if value is None and _net(summary) > 0.0 else float(value or 0.0)
    )


def _net(summary: Mapping[str, object]) -> float:
    return _number(summary, "net_return_bps")


def _number(source: Mapping[str, object], name: str) -> float:
    value = source.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"ETH opposing-breakout {name} must be numeric")
    return float(value)


def _child(source: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = source.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"ETH opposing-breakout {name} must be an object")
    return value
