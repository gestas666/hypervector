"""One-minute, shared-capital replay for flow-exhaustion reversion signals."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping

import numpy as np
import pandas as pd

from hypervector.research.low_tf_multi_asset_replay_risk import (
    adverse_low_tf_price,
    low_tf_liquidation_price,
)
from hypervector.research.flow_exhaustion_replay_models import (
    FlowExitReason,
    FlowExhaustionRejection,
    FlowExhaustionReplayConfig,
    FlowExhaustionReplayReport,
    FlowExhaustionTrade,
)
from hypervector.research.shared_portfolio_models import Direction
from hypervector.research.shared_trade_portfolio import (
    SharedTradeOutcome,
    SharedTradeReplayConfig,
    replay_shared_trade_outcomes,
)

_SIGNAL_COLUMNS = frozenset(
    {
        "symbol",
        "bar_open_at",
        "available_at_utc",
        "side",
        "target_price",
        "stop_price",
        "rank_score",
    }
)
_MINUTE_COLUMNS = frozenset(
    {"timestamp", "open", "high", "low", "close", "funding_rate"}
)
_VENUE_MAX_LEVERAGE: Mapping[str, float] = {"BTC": 40.0, "SOL": 20.0}


def replay_flow_exhaustion_signals(
    minute_bars: Mapping[str, pd.DataFrame],
    signals: pd.DataFrame,
    config: FlowExhaustionReplayConfig | None = None,
) -> FlowExhaustionReplayReport:
    """Replay both symbols and directions through one shared capital ledger."""
    cfg = config or FlowExhaustionReplayConfig()
    paths = _validated_paths(minute_bars)
    ordered = _validated_signals(signals)
    trades: list[FlowExhaustionTrade] = []
    rejections: list[FlowExhaustionRejection] = []
    occupied_until: dict[str, pd.Timestamp] = {}
    for _, row in ordered.iterrows():
        rejection = _occupancy_rejection(row, occupied_until)
        if rejection is not None:
            rejections.append(rejection)
            continue
        trade, rejection = _simulate_signal(paths[str(row["symbol"])], row, cfg)
        if rejection is not None:
            rejections.append(rejection)
            continue
        if trade is None:
            raise RuntimeError("flow-exhaustion simulation returned no outcome")
        trades.append(trade)
        occupied_until[trade.symbol] = pd.Timestamp(trade.exit_time_utc)
    return _shared_report(trades, rejections, cfg)


def _validated_paths(
    minute_bars: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    if not minute_bars:
        raise ValueError("flow-exhaustion replay requires minute paths")
    output: dict[str, pd.DataFrame] = {}
    for raw_symbol, bars in minute_bars.items():
        symbol = raw_symbol.strip().upper()
        if symbol not in _VENUE_MAX_LEVERAGE:
            raise ValueError(f"unsupported minute-path symbol: {symbol}")
        output[symbol] = _validated_minutes(bars)
    return output


def _validated_minutes(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_MINUTE_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"flow-exhaustion minute bars missing: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if bars.empty or times.tz is None or times.has_duplicates:
        raise ValueError("minute path requires non-empty unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("minute path must be ordered")
    values = bars[["open", "high", "low", "close", "funding_rate"]].to_numpy(float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0.0).any():
        raise ValueError("minute path contains invalid price or funding values")
    return bars.set_index("timestamp").copy()


def _validated_signals(signals: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_SIGNAL_COLUMNS.difference(signals.columns))
    if missing:
        raise ValueError(f"flow-exhaustion signals missing: {missing}")
    if signals.empty:
        return signals.copy()
    output = signals.copy()
    output["available_at_utc"] = pd.to_datetime(output["available_at_utc"], utc=True)
    output["bar_open_at"] = pd.to_datetime(output["bar_open_at"], utc=True)
    if output["available_at_utc"].duplicated(keep=False).any():
        duplicate = output.loc[output["available_at_utc"].duplicated(False)]
        if duplicate[["symbol", "side"]].duplicated().any():
            raise ValueError("flow-exhaustion signal identity is duplicated")
    if not output["side"].isin(("long", "short")).all():
        raise ValueError("flow-exhaustion side must be long or short")
    if not output["symbol"].isin(_VENUE_MAX_LEVERAGE).all():
        raise ValueError("flow-exhaustion signal symbol must be BTC or SOL")
    return output.sort_values(
        ["available_at_utc", "rank_score", "symbol"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def _occupancy_rejection(
    row: pd.Series, occupied_until: Mapping[str, pd.Timestamp]
) -> FlowExhaustionRejection | None:
    symbol = str(row["symbol"])
    signal_time = pd.Timestamp(row["available_at_utc"])
    if signal_time < occupied_until.get(symbol, pd.Timestamp.min.tz_localize("UTC")):
        return _rejection(row, "symbol_position_open")
    return None


def _simulate_signal(
    minutes: pd.DataFrame,
    row: pd.Series,
    config: FlowExhaustionReplayConfig,
) -> tuple[FlowExhaustionTrade | None, FlowExhaustionRejection | None]:
    entry_time = pd.Timestamp(row["available_at_utc"])
    if entry_time not in minutes.index:
        return None, _rejection(row, "entry_minute_unavailable")
    direction = _direction(row)
    entry = adverse_low_tf_price(
        float(minutes.loc[entry_time, "open"]),
        direction,
        config.slippage_bps_per_side,
        entering=True,
    )
    target, stop = float(row["target_price"]), float(row["stop_price"])
    reason = _entry_rejection(direction, entry, target, stop, config)
    if reason is not None:
        return None, _rejection(row, reason)
    terms = _position_terms(str(row["symbol"]), direction, entry, stop, config)
    return _walk_path(minutes, row, direction, entry, target, stop, terms, config)


@dataclass(frozen=True)
class _PositionTerms:
    quantity: float
    notional: float
    margin: float
    risk_budget: float
    entry_fee: float


def _position_terms(
    symbol: str,
    direction: Direction,
    entry: float,
    stop: float,
    config: FlowExhaustionReplayConfig,
) -> _PositionTerms:
    stop_fill = adverse_low_tf_price(
        stop, direction, config.slippage_bps_per_side, entering=False
    )
    signed_loss = -_signed_return(direction, entry, stop_fill)
    fee_fraction = config.fee_round_trip_bps / 10_000.0
    loss_fraction = signed_loss + fee_fraction
    desired_notional = config.initial_equity_usd * config.risk_fraction / loss_fraction
    maximum_notional = (
        config.initial_equity_usd * config.maximum_margin_fraction * config.leverage
    )
    notional = min(desired_notional, maximum_notional)
    quantity = notional / entry
    margin = notional / config.leverage
    entry_fee = notional * config.fee_rate_per_side
    return _PositionTerms(
        quantity,
        notional,
        margin,
        config.initial_equity_usd * config.risk_fraction,
        entry_fee,
    )


def _walk_path(
    minutes: pd.DataFrame,
    row: pd.Series,
    direction: Direction,
    entry: float,
    target: float,
    stop: float,
    terms: _PositionTerms,
    config: FlowExhaustionReplayConfig,
) -> tuple[FlowExhaustionTrade | None, FlowExhaustionRejection | None]:
    entry_time = pd.Timestamp(row["available_at_utc"])
    deadline = entry_time + pd.Timedelta(minutes=config.maximum_hold_minutes)
    path = minutes.loc[(minutes.index >= entry_time) & (minutes.index <= deadline)]
    if path.empty:
        return None, _rejection(row, "outcome_path_incomplete")
    funding = 0.0
    expected_timestamp = entry_time
    for timestamp, bar in path.iterrows():
        if timestamp != expected_timestamp:
            return None, _rejection(row, "outcome_path_incomplete")
        if timestamp > entry_time:
            funding += _funding_cashflow(direction, terms.quantity, bar)
        if timestamp >= deadline:
            raw_exit = float(bar["open"])
            return _trade(
                row,
                direction,
                entry,
                raw_exit,
                stop,
                target,
                terms,
                funding,
                "max_hold",
                False,
                config,
            ), None
        outcome = _barrier_outcome(
            row, direction, entry, stop, target, terms, funding, timestamp, bar, config
        )
        if outcome is not None:
            return outcome, None
        expected_timestamp += pd.Timedelta(minutes=1)
    return None, _rejection(row, "outcome_path_incomplete")


def _barrier_outcome(
    row: pd.Series,
    direction: Direction,
    entry: float,
    stop: float,
    target: float,
    terms: _PositionTerms,
    funding: float,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    config: FlowExhaustionReplayConfig,
) -> FlowExhaustionTrade | None:
    liquidation = _liquidation(str(row["symbol"]), direction, entry, terms, funding)
    hits = _barrier_hits(direction, bar, liquidation, stop, target)
    reason = next(
        (name for name in ("liquidation", "stop", "target") if hits[name]), None
    )
    if reason is None:
        return None
    raw_exit = _barrier_price(direction, bar, liquidation, stop, target, reason)
    return _trade(
        row,
        direction,
        entry,
        raw_exit,
        stop,
        target,
        terms,
        funding,
        reason,
        sum(hits.values()) > 1,
        config,
        timestamp + pd.Timedelta(minutes=1),
    )


def _trade(
    row: pd.Series,
    direction: Direction,
    entry: float,
    raw_exit: float,
    stop: float,
    target: float,
    terms: _PositionTerms,
    funding: float,
    reason: FlowExitReason,
    ambiguous: bool,
    config: FlowExhaustionReplayConfig,
    exit_time: pd.Timestamp | None = None,
) -> FlowExhaustionTrade:
    resolved_exit_time = exit_time or (
        pd.Timestamp(row["available_at_utc"])
        + pd.Timedelta(minutes=config.maximum_hold_minutes)
    )
    exit_price = adverse_low_tf_price(
        raw_exit, direction, config.slippage_bps_per_side, entering=False
    )
    gross = terms.quantity * entry * _signed_return(direction, entry, exit_price)
    exit_fee = terms.quantity * exit_price * config.fee_rate_per_side
    net = gross - terms.entry_fee - exit_fee + funding
    liquidation = _liquidation(str(row["symbol"]), direction, entry, terms, funding)
    trade_id = _trade_id(row)
    return FlowExhaustionTrade(
        trade_id,
        str(row["symbol"]),
        direction,
        pd.Timestamp(row["bar_open_at"]).isoformat(),
        pd.Timestamp(row["available_at_utc"]).isoformat(),
        resolved_exit_time.isoformat(),
        entry,
        exit_price,
        stop,
        target,
        liquidation,
        terms.quantity,
        terms.notional,
        terms.margin,
        terms.risk_budget,
        gross,
        terms.entry_fee,
        exit_fee,
        terms.entry_fee + exit_fee,
        funding,
        net,
        net,
        reason,
        ambiguous,
    )


def _shared_report(
    trades: list[FlowExhaustionTrade],
    rejections: list[FlowExhaustionRejection],
    config: FlowExhaustionReplayConfig,
) -> FlowExhaustionReplayReport:
    outcomes = tuple(_shared_outcome(trade, config) for trade in trades)
    shared = replay_shared_trade_outcomes(
        outcomes,
        SharedTradeReplayConfig(initial_equity_usd=config.initial_equity_usd),
    )
    scaled = {trade.trade_id: trade.net_pnl_usd for trade in shared.trades}
    resolved = tuple(
        replace(trade, scaled_net_pnl_usd=scaled[trade.trade_id]) for trade in trades
    )
    scale_by_id = {
        trade.trade_id: trade.scaling_base_usd / config.initial_equity_usd
        for trade in shared.trades
    }
    return FlowExhaustionReplayReport(
        shared.initial_equity_usd,
        shared.final_equity_usd,
        shared.net_pnl_usd,
        shared.return_pct,
        shared.completed_trades,
        shared.wins,
        shared.losses,
        shared.profit_factor,
        shared.realized_maximum_drawdown_pct,
        shared.maximum_concurrent_positions,
        sum(trade.fees_usd * scale_by_id[trade.trade_id] for trade in resolved),
        sum(
            trade.funding_cashflow_usd * scale_by_id[trade.trade_id]
            for trade in resolved
        ),
        sum(trade.exit_reason == "liquidation" for trade in resolved),
        resolved,
        tuple(rejections),
    )


def _shared_outcome(
    trade: FlowExhaustionTrade, config: FlowExhaustionReplayConfig
) -> SharedTradeOutcome:
    return SharedTradeOutcome(
        trade.trade_id,
        trade.symbol,
        _timestamp_ms(trade.entry_time_utc),
        _timestamp_ms(trade.exit_time_utc),
        config.initial_equity_usd,
        trade.isolated_margin_usd / config.initial_equity_usd,
        trade.entry_fee_usd,
        trade.net_pnl_usd,
        trade.exit_reason,
    )


def _entry_rejection(
    direction: Direction,
    entry: float,
    target: float,
    stop: float,
    config: FlowExhaustionReplayConfig,
) -> str | None:
    if not all(math.isfinite(value) and value > 0.0 for value in (target, stop)):
        return "invalid_barrier"
    if _signed_return(direction, entry, target) * 10_000.0 < config.minimum_target_bps:
        return "entry_edge_dissipated"
    if _signed_return(direction, entry, stop) >= 0.0:
        return "stop_crossed_at_entry"
    return None


def _barrier_hits(
    direction: Direction,
    bar: pd.Series,
    liquidation: float,
    stop: float,
    target: float,
) -> dict[str, bool]:
    high, low = float(bar["high"]), float(bar["low"])
    if direction == "long":
        return {
            "liquidation": low <= liquidation,
            "stop": low <= stop,
            "target": high >= target,
        }
    return {
        "liquidation": high >= liquidation,
        "stop": high >= stop,
        "target": low <= target,
    }


def _barrier_price(
    direction: Direction,
    bar: pd.Series,
    liquidation: float,
    stop: float,
    target: float,
    reason: str,
) -> float:
    barrier = {"liquidation": liquidation, "stop": stop, "target": target}[reason]
    if reason == "target":
        return barrier
    bar_open = float(bar["open"])
    return min(barrier, bar_open) if direction == "long" else max(barrier, bar_open)


def _liquidation(
    symbol: str,
    direction: Direction,
    entry: float,
    terms: _PositionTerms,
    funding: float,
) -> float:
    return low_tf_liquidation_price(
        symbol=symbol,
        direction=direction,
        quantity=terms.quantity,
        entry_price=entry,
        isolated_margin=terms.margin,
        entry_fee=terms.entry_fee,
        funding_cashflow=funding,
        venue_max_leverage=_VENUE_MAX_LEVERAGE[symbol],
    )


def _funding_cashflow(direction: Direction, quantity: float, bar: pd.Series) -> float:
    sign = 1.0 if direction == "long" else -1.0
    return -sign * quantity * float(bar["open"]) * float(bar["funding_rate"])


def _signed_return(direction: Direction, entry: float, exit_price: float) -> float:
    sign = 1.0 if direction == "long" else -1.0
    return sign * (exit_price / entry - 1.0)


def _direction(row: pd.Series) -> Direction:
    return "long" if str(row["side"]) == "long" else "short"


def _rejection(row: pd.Series, reason: str) -> FlowExhaustionRejection:
    return FlowExhaustionRejection(
        str(row["symbol"]),
        pd.Timestamp(row["available_at_utc"]).isoformat(),
        str(row["side"]),
        reason,
    )


def _trade_id(row: pd.Series) -> str:
    timestamp = pd.Timestamp(row["available_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
    return f"flow-exhaustion-{str(row['symbol']).lower()}-{timestamp}-{row['side']}"


def _timestamp_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
