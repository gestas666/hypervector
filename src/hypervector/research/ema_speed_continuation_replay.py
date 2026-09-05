"""Economic and technical-path replay for the EMA-speed challenger."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.ema_speed_continuation import (
    EmaSpeedContinuationConfig,
    build_ema_speed_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.shared_trade_portfolio import (
    SharedTradeOutcome,
    SharedTradeReplayConfig,
    SharedTradeReplayReport,
    replay_shared_trade_outcomes,
)


_QUOTE_COLUMNS = (
    "entry_bid",
    "entry_ask",
    "close_bid",
    "close_ask",
    "risk_low",
    "risk_high",
    "first_boundary_delay_ms",
    "end_boundary_age_ms",
)


@dataclass(frozen=True)
class EmaSpeedSymbolResult:
    """One symbol's economic replay and non-promotional path assessment."""

    symbol: str
    report: SharedPortfolioReport
    technical_path: dict[str, object]


def evaluate_ema_speed_symbol(
    bars: pd.DataFrame,
    symbol: str,
    slippage_bps_per_side: float,
) -> EmaSpeedSymbolResult:
    """Replay one frozen symbol using exact next-boundary executable quotes."""
    normalized = symbol.strip().upper()
    if normalized not in {"BTC", "SOL"}:
        raise ValueError("EMA-speed replay symbol must be BTC or SOL")
    if not math.isfinite(slippage_bps_per_side) or slippage_bps_per_side < 0.0:
        raise ValueError("EMA-speed slippage must be finite and non-negative")
    signal_config = EmaSpeedContinuationConfig()
    signals = build_ema_speed_signals(bars, signal_config)
    market, aligned = _replay_rows(bars, signals)
    report = evaluate_shared_bar_portfolio(
        market,
        aligned,
        _portfolio_config(normalized, slippage_bps_per_side),
    )
    path = _technical_path(market, report)
    return EmaSpeedSymbolResult(normalized, report, path)


def combine_ema_speed_reports(
    results: tuple[EmaSpeedSymbolResult, ...],
    *,
    initial_equity_usd: float,
) -> SharedTradeReplayReport:
    """Scale symbol lifecycles through one chronological shared account."""
    symbols = tuple(result.symbol for result in results)
    if set(symbols) != {"BTC", "SOL"} or len(symbols) != 2:
        raise ValueError("EMA-speed shared replay requires exactly BTC and SOL")
    outcomes = tuple(
        outcome for result in results for outcome in _shared_outcomes(result)
    )
    return replay_shared_trade_outcomes(
        outcomes,
        SharedTradeReplayConfig(initial_equity_usd=initial_equity_usd),
    )


def _portfolio_config(symbol: str, slippage: float) -> SharedPortfolioConfig:
    venue_max = 40.0 if symbol == "BTC" else 20.0
    return SharedPortfolioConfig(
        symbol=symbol,
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=venue_max,
        maximum_stop_distance_bps=80.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        max_hold_bars=16,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=False,
        open_bid_column="entry_bid",
        open_ask_column="entry_ask",
        close_bid_column="close_bid",
        close_ask_column="close_ask",
        risk_high_column="risk_high",
        risk_low_column="risk_low",
    )


def _replay_rows(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = sorted(set(_QUOTE_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"EMA-speed replay bars missing columns: {missing}")
    numeric = bars[list(_QUOTE_COLUMNS)].astype(float)
    finite = pd.Series(np.isfinite(numeric).all(axis=1), index=bars.index)
    valid = bars["source_complete"].astype(bool) & finite
    market = bars.loc[valid].copy()
    if len(market) < 2:
        raise ValueError("EMA-speed replay has insufficient executable rows")
    elapsed = market.index.to_series().diff().dt.total_seconds().div(900.0)
    market["gap_before_bars"] = elapsed.sub(1.0).clip(lower=0.0).fillna(0).astype(int)
    return market, signals.loc[market.index].copy()


def _technical_path(
    market: pd.DataFrame,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    unresolved: list[str] = []
    for trade in report.trades:
        lifecycle = market.iloc[trade.entry_position : trade.exit_position + 1]
        if not lifecycle["l2_path_complete"].astype(bool).all():
            unresolved.append(f"{trade.entry_time_utc}|{trade.direction}")
    return {
        "completed_lifecycles": report.completed_trades,
        "l2_unresolved_lifecycles": len(unresolved),
        "l2_unresolved_lifecycle_ids": unresolved,
        "mark_path_status": "unresolved_not_available",
        "mark_unresolved_lifecycles": report.completed_trades,
        "qualification_ready": False,
        "qualification_reason": "exact_historical_mark_path_not_available",
    }


def _shared_outcomes(
    result: EmaSpeedSymbolResult,
) -> tuple[SharedTradeOutcome, ...]:
    records: list[SharedTradeOutcome] = []
    for position, trade in enumerate(result.report.trades):
        entry_ms = _timestamp_ms(trade.entry_time_utc)
        exit_ms = max(_timestamp_ms(trade.exit_time_utc), entry_ms + 1)
        entry_fee = trade.quantity * trade.entry_price * 0.00045
        records.append(
            SharedTradeOutcome(
                trade_id=f"ema5|{result.symbol}|{entry_ms}|{position:06d}",
                symbol=result.symbol,
                entry_time_ms=entry_ms,
                exit_time_ms=exit_ms,
                source_equity_usd=trade.equity_before_usd,
                margin_fraction=trade.margin_usd / trade.equity_before_usd,
                entry_fee_usd=entry_fee,
                net_pnl_usd=trade.net_pnl_usd,
                outcome=trade.exit_reason,
            )
        )
    return tuple(records)


def _timestamp_ms(value: str) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("EMA-speed trade timestamps must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)
