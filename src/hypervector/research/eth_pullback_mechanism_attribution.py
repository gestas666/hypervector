"""Causal side and breakout-relation attribution for the ETH pullback rule."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
import math
from statistics import mean, median

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitTrade

_SIDES = ("long", "short")
_RELATIONS = ("aligned", "opposed")


@dataclass(frozen=True)
class _AttributedTrade:
    signal_time: pd.Timestamp
    side: str
    relation: str
    trade: HypeExitTrade


def build_eth_pullback_mechanism_attribution(
    market: pd.DataFrame,
    trades: Sequence[HypeExitTrade],
    *,
    development_end_utc: str,
    opened_final_start_utc: str,
    opened_final_end_utc: str,
) -> dict[str, object]:
    """Partition exact ETH lifecycles by side and breakout-side relation."""
    development_end, final_start, final_end = _boundaries(
        development_end_utc,
        opened_final_start_utc,
        opened_final_end_utc,
    )
    attributed = _attribute_trades(market, trades)
    development = tuple(row for row in attributed if row.signal_time < development_end)
    final = tuple(
        row for row in attributed if final_start <= row.signal_time < final_end
    )
    selected = development + final
    return {
        "schema_version": 1,
        "mode": "eth_pullback_side_breakout_relation_attribution_v1",
        "contract": _contract(),
        "split": {
            "development_end_exclusive_utc": development_end.isoformat(),
            "opened_final_start_utc": final_start.isoformat(),
            "opened_final_end_exclusive_utc": final_end.isoformat(),
        },
        "coverage": {
            "input_trades": len(attributed),
            "development_trades": len(development),
            "opened_final_trades": len(final),
            "purge_or_out_of_window_trades": len(attributed) - len(selected),
        },
        "segments": {
            "development": _segment_report(development),
            "opened_final_60d": _segment_report(final),
            "all_available": _segment_report(selected),
        },
        "limitations": _limitations(),
    }


def _boundaries(
    development_end_utc: str,
    final_start_utc: str,
    final_end_utc: str,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    values = tuple(
        pd.Timestamp(value)
        for value in (development_end_utc, final_start_utc, final_end_utc)
    )
    if any(value.tzinfo is None for value in values):
        raise ValueError("ETH attribution boundaries must be timezone-aware")
    normalized = tuple(value.tz_convert("UTC") for value in values)
    if not normalized[0] < normalized[1] < normalized[2]:
        raise ValueError("ETH attribution boundaries must be strictly increasing")
    return normalized


def _attribute_trades(
    market: pd.DataFrame,
    trades: Sequence[HypeExitTrade],
) -> tuple[_AttributedTrade, ...]:
    _validate_market(market)
    rows = tuple(_attribute_trade(market, trade) for trade in trades)
    timestamps = [row.signal_time for row in rows]
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("ETH attribution trade signal timestamps must be unique")
    return tuple(sorted(rows, key=lambda row: row.signal_time))


def _attribute_trade(
    market: pd.DataFrame,
    trade: HypeExitTrade,
) -> _AttributedTrade:
    signal_time = pd.Timestamp(trade.signal_time_utc)
    if signal_time.tzinfo is None:
        raise ValueError("ETH attribution trade signal time must be timezone-aware")
    signal_time = signal_time.tz_convert("UTC")
    if signal_time not in market.index:
        raise ValueError("ETH attribution trade signal time is missing from market")
    side = _side(trade.side, "trade side")
    source_side = _side(market.at[signal_time, "entry_side"], "market entry side")
    if source_side != side:
        raise ValueError("ETH attribution trade side does not match market entry side")
    breakout_side = _side(market.at[signal_time, "breakout_side"], "breakout side")
    relation = "aligned" if breakout_side == side else "opposed"
    return _AttributedTrade(signal_time, side, relation, trade)


def _validate_market(market: pd.DataFrame) -> None:
    missing = sorted({"entry_side", "breakout_side"}.difference(market.columns))
    if missing:
        raise ValueError(f"ETH attribution market missing columns: {missing}")
    if not isinstance(market.index, pd.DatetimeIndex) or market.index.tz is None:
        raise ValueError("ETH attribution market index must be timezone-aware")
    if market.index.has_duplicates or not market.index.is_monotonic_increasing:
        raise ValueError("ETH attribution market index must be ordered and unique")


def _segment_report(rows: Sequence[_AttributedTrade]) -> dict[str, object]:
    return {
        "all": _summary(rows),
        "by_side": {side: _summary(_filter(rows, side=side)) for side in _SIDES},
        "by_relation": {
            relation: _summary(_filter(rows, relation=relation))
            for relation in _RELATIONS
        },
        "by_side_relation": {
            f"{side}|{relation}": _summary(_filter(rows, side=side, relation=relation))
            for side in _SIDES
            for relation in _RELATIONS
        },
    }


def _filter(
    rows: Sequence[_AttributedTrade],
    *,
    side: str | None = None,
    relation: str | None = None,
) -> tuple[_AttributedTrade, ...]:
    return tuple(
        row
        for row in rows
        if (side is None or row.side == side)
        and (relation is None or row.relation == relation)
    )


def _summary(rows: Sequence[_AttributedTrade]) -> dict[str, object]:
    values = [float(row.trade.net_return_bps) for row in rows]
    favorable = [float(row.trade.maximum_favorable_excursion_bps) for row in rows]
    adverse = [float(row.trade.maximum_adverse_excursion_bps) for row in rows]
    for value in (*values, *favorable, *adverse):
        if not math.isfinite(value):
            raise ValueError("ETH attribution trade economics must be finite")
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": sum(value == 0.0 for value in values),
        "net_return_bps": sum(values),
        "mean_return_bps": mean(values) if values else None,
        "median_return_bps": median(values) if values else None,
        "profit_factor": sum(wins) / sum(losses) if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "net_excluding_largest_winner_bps": (
            sum(values) - max(wins) if wins else sum(values)
        ),
        "mean_mfe_bps": mean(favorable) if favorable else None,
        "median_mfe_bps": median(favorable) if favorable else None,
        "mean_mae_bps": mean(adverse) if adverse else None,
        "median_mae_bps": median(adverse) if adverse else None,
        "exit_reasons": dict(
            sorted(Counter(row.trade.exit_reason for row in rows).items())
        ),
    }


def _maximum_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _side(value: object, label: str) -> str:
    if not isinstance(value, str) or value not in _SIDES:
        raise ValueError(f"ETH attribution {label} must be long or short")
    return value


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "entry_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "the opened final 60-day block was previously inspected and is descriptive",
        "the exact ETH entry and stop-hold shape was selected after multiple trials",
        "one-minute bars do not reproduce private IOC latency or intrabar stop ordering",
        "subgroup results have fewer effective samples than the pooled route",
        "attribution describes the frozen rule and cannot select or execute a successor",
    ]
