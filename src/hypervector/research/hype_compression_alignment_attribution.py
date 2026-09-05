"""Frozen-policy HYPE compression entry-relation attribution."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
import math
from statistics import mean, median

import pandas as pd

FROZEN_HYPE_COMPRESSION_POLICY_ID = "compression_5m50_1m40_pullback"
_SIDES = ("long", "short")
_RELATIONS = ("aligned", "opposed")
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class _AttributedTrade:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    side: str
    relation: str
    net_bps: float
    mfe_bps: float
    mae_bps: float
    exit_reason: str


def build_hype_compression_alignment_attribution(
    development_market: pd.DataFrame,
    development_trades: pd.DataFrame,
    confirmation_markets: Sequence[pd.DataFrame],
    confirmation_trades: pd.DataFrame,
    *,
    frozen_policy_id: str,
    fold_count: int = 5,
) -> dict[str, object]:
    """Attribute the exact frozen HYPE policy without replay or reselection."""
    _require_frozen_policy(frozen_policy_id)
    _validate_fold_count(fold_count)
    development_source = _validated_market(development_market)
    confirmation_source = _combine_markets(confirmation_markets)
    development_rows, development_coverage = _attributed_segment(
        development_source, development_trades, frozen_policy_id
    )
    confirmation_rows, confirmation_coverage = _attributed_segment(
        confirmation_source, confirmation_trades, frozen_policy_id
    )
    boundaries = _fold_boundaries(development_source.index, fold_count)
    return {
        "schema_version": 1,
        "mode": "hype_compression_entry_alignment_attribution_v1",
        "contract": _contract(frozen_policy_id, fold_count),
        "coverage": {
            "development": development_coverage,
            "later_confirmation": confirmation_coverage,
        },
        "segments": {
            "development": _segment_report(development_rows, boundaries),
            "later_confirmation": _segment_report(confirmation_rows, None),
        },
        "limitations": _limitations(),
    }


def _attributed_segment(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    policy_id: str,
) -> tuple[tuple[_AttributedTrade, ...], dict[str, int]]:
    selected = _selected_trade_rows(trades, policy_id)
    censored = _censored_mask(selected)
    resolved = selected.loc[~censored]
    if resolved.empty:
        rows: tuple[_AttributedTrade, ...] = ()
    else:
        if market.empty:
            raise ValueError("HYPE attribution market is empty for resolved trades")
        rows = tuple(_attribute_trade(market, row) for _, row in resolved.iterrows())
        rows = tuple(sorted(rows, key=lambda row: row.entry_time))
    coverage = {
        "input_selected_rows": len(selected),
        "resolved_rows": len(rows),
        "censored_rows": int(censored.sum()),
    }
    return rows, coverage


def _selected_trade_rows(trades: pd.DataFrame, policy_id: str) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    if "policy_id" not in trades:
        raise ValueError("HYPE attribution trades require policy_id")
    selected = trades.loc[trades["policy_id"].eq(policy_id)].copy()
    if selected.empty:
        raise ValueError("HYPE attribution has no rows for frozen policy")
    return selected


def _censored_mask(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(False, index=trades.index, dtype=bool)
    if "censored" not in trades:
        return pd.Series(False, index=trades.index, dtype=bool)
    values = trades["censored"]
    if not values.map(lambda value: isinstance(value, bool)).all():
        raise ValueError("HYPE attribution censored flags must be boolean")
    return values.astype(bool)


def _attribute_trade(market: pd.DataFrame, row: pd.Series) -> _AttributedTrade:
    required = {
        "side",
        "signal_time_utc",
        "entry_time_utc",
        "net_return_bps",
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "exit_reason",
    }
    missing = sorted(required.difference(row.index))
    if missing:
        raise ValueError(f"HYPE attribution trade missing fields: {missing}")
    signal_time = _timestamp(row["signal_time_utc"], "signal time")
    entry_time = _timestamp(row["entry_time_utc"], "entry time")
    if signal_time not in market.index:
        raise ValueError("HYPE attribution signal time is missing from market")
    side = _side(row["side"], "trade side")
    source_side = _side(market.at[signal_time, "entry_side"], "market entry side")
    if side != source_side:
        raise ValueError("HYPE attribution trade side does not match market entry side")
    breakout = _side(market.at[signal_time, "breakout_side"], "breakout side")
    return _AttributedTrade(
        signal_time,
        entry_time,
        side,
        "aligned" if side == breakout else "opposed",
        _number(row["net_return_bps"], "net return"),
        _number(row["maximum_favorable_excursion_bps"], "MFE"),
        _number(row["maximum_adverse_excursion_bps"], "MAE"),
        _text(row["exit_reason"], "exit reason"),
    )


def _segment_report(
    rows: Sequence[_AttributedTrade],
    boundaries: pd.DatetimeIndex | None,
) -> dict[str, object]:
    return {
        "lifecycles": [_lifecycle_record(row) for row in rows],
        "overall": _summary(rows, boundaries),
        "by_relation": {
            relation: _summary(_filter(rows, relation=relation), boundaries)
            for relation in _RELATIONS
        },
        "by_side": {
            side: _summary(_filter(rows, side=side), boundaries) for side in _SIDES
        },
        "by_side_relation": {
            f"{side}|{relation}": _summary(
                _filter(rows, side=side, relation=relation), boundaries
            )
            for side in _SIDES
            for relation in _RELATIONS
        },
    }


def _lifecycle_record(row: _AttributedTrade) -> dict[str, object]:
    return {
        "signal_time_utc": row.signal_time.isoformat(),
        "entry_time_utc": row.entry_time.isoformat(),
        "side": row.side,
        "breakout_side_relation": row.relation,
        "net_return_bps": row.net_bps,
        "maximum_favorable_excursion_bps": row.mfe_bps,
        "maximum_adverse_excursion_bps": row.mae_bps,
        "exit_reason": row.exit_reason,
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


def _summary(
    rows: Sequence[_AttributedTrade],
    boundaries: pd.DatetimeIndex | None,
) -> dict[str, object]:
    values = [row.net_bps for row in rows]
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    result: dict[str, object] = {
        "trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": sum(value == 0.0 for value in values),
        "net_return_bps": sum(values),
        "mean_return_bps": mean(values) if values else None,
        "median_return_bps": median(values) if values else None,
        "profit_factor": sum(wins) / sum(losses) if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "net_excluding_largest_winner_bps": sum(values) - max(wins, default=0.0),
        "mean_mfe_bps": mean(row.mfe_bps for row in rows) if rows else None,
        "mean_mae_bps": mean(row.mae_bps for row in rows) if rows else None,
        "exit_reasons": dict(sorted(Counter(row.exit_reason for row in rows).items())),
    }
    if boundaries is not None:
        fold_net = _fold_net(rows, boundaries)
        result.update(
            fold_net_bps=fold_net,
            positive_folds=sum(value > 0.0 for value in fold_net),
            median_fold_net_bps=median(fold_net),
        )
    return result


def _fold_net(
    rows: Sequence[_AttributedTrade], boundaries: pd.DatetimeIndex
) -> list[float]:
    output = [0.0] * (len(boundaries) - 1)
    for row in rows:
        position = int(boundaries.searchsorted(row.entry_time, side="right") - 1)
        output[min(max(position, 0), len(output) - 1)] += row.net_bps
    return output


def _fold_boundaries(index: pd.DatetimeIndex, fold_count: int) -> pd.DatetimeIndex:
    start = index[0]
    end = index[-1] + _MINUTE
    step = (end.value - start.value) // fold_count
    values = [start.value + step * position for position in range(fold_count)]
    values.append(end.value)
    return pd.to_datetime(values, utc=True)


def _combine_markets(markets: Sequence[pd.DataFrame]) -> pd.DataFrame:
    if not markets:
        return pd.DataFrame(columns=["entry_side", "breakout_side"])
    validated = [_validated_market(market) for market in markets]
    combined = pd.concat(validated).sort_index()
    if combined.index.has_duplicates:
        raise ValueError("HYPE attribution confirmation markets overlap")
    return combined


def _validated_market(market: pd.DataFrame) -> pd.DataFrame:
    missing = sorted({"entry_side", "breakout_side"}.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE attribution market missing columns: {missing}")
    if market.empty or not isinstance(market.index, pd.DatetimeIndex):
        raise ValueError("HYPE attribution market requires DatetimeIndex rows")
    if market.index.tz is None or market.index.has_duplicates:
        raise ValueError("HYPE attribution market timestamps must be unique and aware")
    if not market.index.is_monotonic_increasing:
        raise ValueError("HYPE attribution market timestamps must be ordered")
    return market


def _maximum_drawdown(values: Sequence[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _require_frozen_policy(policy_id: str) -> None:
    if policy_id != FROZEN_HYPE_COMPRESSION_POLICY_ID:
        raise ValueError("frozen HYPE compression policy identity is required")


def _validate_fold_count(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise ValueError("HYPE attribution fold_count must be at least two")


def _side(value: object, label: str) -> str:
    if not isinstance(value, str) or value not in _SIDES:
        raise ValueError(f"HYPE attribution {label} must be long or short")
    return value


def _timestamp(value: object, label: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError(f"HYPE attribution {label} must be timezone-aware")
    return stamp.tz_convert("UTC")


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"HYPE attribution {label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"HYPE attribution {label} must be finite")
    return output


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE attribution {label} must be non-empty text")
    return value


def _contract(policy_id: str, fold_count: int) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "selection_performed": False,
        "frozen_policy_id": policy_id,
        "chronological_fold_count": fold_count,
        "relation_source": "completed_5m_breakout_direction_at_signal_time",
    }


def _limitations() -> list[str]:
    return [
        "the relation subgroup was inspected after the frozen compression policy",
        "the later confirmation block was previously opened and is descriptive",
        "subgroup attribution does not replay a gate or change position occupancy",
        "one-minute replay cannot prove private IOC latency or intrabar ordering",
        "the result cannot filter, size, route, retain, close, or promote a trade",
    ]
