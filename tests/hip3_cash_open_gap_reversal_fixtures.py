"""Exact-shape fixtures for cash-open gap-reversal research tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows


def archive_bars() -> tuple[pd.DataFrame, MuChronologicalWindows]:
    """Return three development events and sealed later partitions."""
    index = pd.date_range(
        "2026-06-08", "2026-06-15", freq="15min", inclusive="left", tz="UTC"
    )
    signal_close = np.full(len(index), 100.0)
    frame = _base_frame(index, signal_close)
    _event(frame, "2026-06-09T13:30:00Z", 101.0, 100.9, "target")
    _event(frame, "2026-06-11T13:30:00Z", 99.0, 99.1, "target")
    _event(frame, "2026-06-12T13:30:00Z", 101.0, 100.9, "stop")
    windows = MuChronologicalWindows(
        index[0],
        index[480],
        index[576],
        index[-1] + pd.Timedelta(minutes=15),
        ((index[0], index[160]), (index[160], index[320]), (index[320], index[480])),
    )
    return frame, windows


def execution(symbol: str = "xyz:SP500") -> MuArchiveExecution:
    """Return the exact-sized, low-friction unit execution contract."""
    return MuArchiveExecution(
        effective_taker_fee_rate=0.00001,
        notional_usd=5000.0,
        venue_max_leverage=20.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=0.0,
        fixed_stop_bps=80.0,
        maximum_hold_bars=25,
        risk_high_column="risk_high",
        risk_low_column="risk_low",
        entry_risk_high_column="risk_entry_high",
        entry_risk_low_column="risk_entry_low",
        symbol=symbol,
    )


def _base_frame(index: pd.DatetimeIndex, signal_close: np.ndarray) -> pd.DataFrame:
    """Build complete exact-source columns with resolved paths."""
    return pd.DataFrame(
        {
            "open": signal_close,
            "high": signal_close + 0.05,
            "low": signal_close - 0.05,
            "close": signal_close,
            "signal_open": signal_close,
            "signal_high": signal_close + 0.05,
            "signal_low": signal_close - 0.05,
            "signal_close": signal_close,
            "signal_gap_before_bars": 0,
            "signal_ohlc_source": "0xarchive_public_trade_ohlc_v1",
            "signal_ohlc_synthetic_no_trade": False,
            "entry_bid": signal_close - 0.01,
            "entry_ask": signal_close + 0.01,
            "decision_bid": signal_close - 0.01,
            "decision_ask": signal_close + 0.01,
            "decision_imbalance_10": 0.0,
            "first_boundary_delay_ms": 100.0,
            "end_boundary_age_ms": 100.0,
            "maximum_snapshot_interval_ms": 100.0,
            "source_snapshot_count": 10,
            "gap_before_bars": 0,
            "funding_rate": 0.0,
            "risk_high": signal_close + 0.05,
            "risk_low": signal_close - 0.05,
            "risk_entry_high": signal_close + 0.05,
            "risk_entry_low": signal_close - 0.05,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100.0,
            "mark_snapshot_count": 100,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": True,
            "entry_maximum_mark_interval_ms": 100.0,
            "entry_mark_snapshot_count": 100,
        },
        index=index,
    )


def _event(
    frame: pd.DataFrame,
    decision: str,
    opening: float,
    close: float,
    outcome: str,
) -> None:
    """Attach one cash-open decision and its next-bar target or stop path."""
    decision_time = pd.Timestamp(decision)
    entry_time = decision_time + pd.Timedelta(minutes=15)
    frame.loc[
        decision_time, ["signal_open", "signal_high", "signal_low", "signal_close"]
    ] = [
        opening,
        max(opening, close) + 0.05,
        min(opening, close) - 0.05,
        close,
    ]
    frame.loc[entry_time, ["open", "high", "low", "close"]] = close
    frame.loc[entry_time, ["entry_bid", "decision_bid"]] = close - 0.01
    frame.loc[entry_time, ["entry_ask", "decision_ask"]] = close + 0.01
    if outcome == "target":
        frame.loc[entry_time, "risk_low" if opening > 100.0 else "risk_high"] = (
            99.9 if opening > 100.0 else 100.1
        )
        frame.loc[
            entry_time, "risk_entry_low" if opening > 100.0 else "risk_entry_high"
        ] = 99.9 if opening > 100.0 else 100.1
    else:
        frame.loc[entry_time, ["risk_high", "risk_entry_high"]] = 101.8
