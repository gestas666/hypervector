"""Continuity-fill dependence attribution for residual research evidence."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from hypervector.research.cross_asset_residual_models import (
    ResidualSignal,
    ResidualTrade,
)

_SUPPORTED_SOURCES = {"hl", "hl_gap_fill"}


def build_residual_gap_audit(
    *,
    left_symbol: str,
    right_symbol: str,
    minute_frames: dict[str, pd.DataFrame],
    signals: Sequence[ResidualSignal],
    trades: Sequence[ResidualTrade],
) -> dict[str, object]:
    """Attribute synthetic continuity-fill exposure without hiding affected rows."""
    symbols = (left_symbol, right_symbol)
    if tuple(minute_frames) != symbols:
        raise ValueError("residual gap audit frames must match ordered pair identity")
    by_symbol = {
        symbol: _gap_times(minute_frames[symbol], symbol) for symbol in symbols
    }
    pair_gaps = by_symbol[left_symbol].union(by_symbol[right_symbol]).sort_values()
    formation = sum(_formation_affected(signal, pair_gaps) for signal in signals)
    decisions = sum(_decision_affected(signal, pair_gaps) for signal in signals)
    affected = [trade for trade in trades if _trade_affected(trade, pair_gaps)]
    affected_net = sum(trade.net_pnl_usd for trade in affected)
    total_net = sum(trade.net_pnl_usd for trade in trades)
    return {
        "left_symbol": left_symbol,
        "right_symbol": right_symbol,
        "gap_minutes_by_symbol": {symbol: len(by_symbol[symbol]) for symbol in symbols},
        "pair_gap_minutes": len(pair_gaps),
        "total_signals": len(signals),
        "formation_affected_signals": formation,
        "decision_bucket_affected_signals": decisions,
        "total_trades": len(trades),
        "lifecycle_affected_trades": len(affected),
        "lifecycle_affected_liquidations": sum(
            trade.exit_reason == "liquidation" for trade in affected
        ),
        "lifecycle_affected_net_pnl_usd": affected_net,
        "unaffected_net_pnl_usd": total_net - affected_net,
        "interpretation": (
            "affected evidence depends on continuity-filled minutes and cannot "
            "reconstruct the missing venue path"
        ),
    }


def _gap_times(frame: pd.DataFrame, symbol: str) -> pd.DatetimeIndex:
    missing = {"timestamp", "source"}.difference(frame.columns)
    if missing:
        raise ValueError(
            f"{symbol} gap audit source missing columns: {sorted(missing)}"
        )
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError(f"{symbol} gap audit timestamps must be ordered and aware")
    sources = frame["source"].astype(str)
    if not sources.isin(_SUPPORTED_SOURCES).all():
        raise ValueError(f"{symbol} gap audit contains unsupported source labels")
    return times[sources.eq("hl_gap_fill").to_numpy()]


def _formation_affected(
    signal: ResidualSignal,
    gaps: pd.DatetimeIndex,
) -> bool:
    start = _aware(signal.fit_start_utc, "signal fit start")
    decision = _aware(signal.decision_time_utc, "signal decision")
    return bool(((gaps >= start) & (gaps < decision)).any())


def _decision_affected(
    signal: ResidualSignal,
    gaps: pd.DatetimeIndex,
) -> bool:
    decision = _aware(signal.decision_time_utc, "signal decision")
    start = decision - pd.Timedelta(minutes=5)
    return bool(((gaps >= start) & (gaps < decision)).any())


def _trade_affected(
    trade: ResidualTrade,
    gaps: pd.DatetimeIndex,
) -> bool:
    entry = _aware(trade.entry_time_utc, "trade entry")
    exit_time = _aware(trade.exit_time_utc, "trade exit")
    return bool(((gaps >= entry) & (gaps < exit_time)).any())


def _aware(value: str, label: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")
