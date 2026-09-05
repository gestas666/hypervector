"""Corrected five-minute Hypertrader impulse transfer for ZEC research."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math
from pathlib import Path

import pandas as pd

from hypervector.research.causal_screen_inputs import load_causal_bar_window
from hypervector.research.fixed_risk_signal_screen import (
    DEFAULT_PROFILES,
    FrictionProfile,
    scored_inputs,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.zec_native15_transfer_screen import build_profile_report

HYPOTHESIS_ID = "v83-zec-corrected-hypertrader-impulse-transfer-20260903"
STRATEGY_ID = "zec_hypertrader_impulse_5m_long_corrected_v1"

_BAR_DELTA = pd.Timedelta(minutes=5)
_ROLLING_HISTORY_BARS = 60
_MINIMUM_INDICATOR_BARS = 30
_EMA_LENGTH = 21
_DIRECTIONAL_LENGTH = 14
_ATR_LENGTH = 14
_MAXIMUM_CLOSE_VS_EMA_BPS = -20.0
_MAXIMUM_DI_DELTA = -40.0
_MAXIMUM_ROC_5_PCT = -0.20
_STOP_ATR_MULTIPLE = 0.500732
_TARGET_R_MULTIPLE = 7.987184761509152


def build_impulse_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """Build causal completed-bar gates and ATR stop anchors with gap resets."""
    _validate_bars(bars)
    long_entry = pd.Series(False, index=bars.index, dtype=bool)
    stop_price = pd.Series(float("nan"), index=bars.index, dtype=float)
    groups = bars.index.to_series().diff().ne(_BAR_DELTA).cumsum()
    for _, segment in bars.groupby(groups, sort=False):
        _build_segment_signals(segment, long_entry, stop_price)
    inactive = pd.Series(False, index=bars.index, dtype=bool)
    return pd.DataFrame(
        {
            "long_entry": long_entry,
            "short_entry": inactive,
            "long_exit": inactive.copy(),
            "short_exit": inactive.copy(),
            "long_signal_name": STRATEGY_ID,
            "short_signal_name": "inactive_short",
            "stop_price": stop_price,
        },
        index=bars.index,
    )


def portfolio_config(profile: FrictionProfile) -> SharedPortfolioConfig:
    """Return the corrected V83 leverage, wall-clock, and cost contract."""
    return SharedPortfolioConfig(
        symbol="ZEC",
        initial_equity=5_000.0,
        margin_fraction=0.02,
        leverage=5.0,
        venue_max_leverage=10.0,
        maximum_notional_usd=500.0,
        target_r_multiple=_TARGET_R_MULTIPLE,
        minimum_stop_distance_bps=20.0,
        maximum_stop_distance_bps=250.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=profile.slippage_bps,
        market_exit_slippage_bps=profile.slippage_bps,
        max_hold_seconds=1_380,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=False,
    )


def profile_supported(metrics: Mapping[str, object]) -> bool:
    """Apply the complete V83 trade, tail, drawdown, and stability gate."""
    completed = _integer_metric(metrics, "completed_trades")
    net = _float_metric(metrics, "net_pnl_usd")
    raw_factor = metrics.get("profit_factor")
    factor = None if raw_factor is None else _float_metric(metrics, "profit_factor")
    ex_largest = _float_metric(metrics, "net_excluding_largest_winner_usd")
    drawdown = _float_metric(metrics, "maximum_drawdown_pct")
    liquidations = _integer_metric(metrics, "liquidations")
    insolvent = metrics.get("insolvent")
    monthly = _monthly_metrics(metrics)
    positive_fraction = sum(value > 0.0 for value in monthly.values()) / len(monthly)
    return bool(
        completed >= 30
        and net > 0.0
        and factor is not None
        and factor > 1.0
        and ex_largest > 0.0
        and drawdown >= -5.0
        and positive_fraction >= 0.5
        and liquidations == 0
        and insolvent is False
    )


def run_partition_screen(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
) -> dict[str, object]:
    """Evaluate one gap-free V83 partition without execution authority."""
    bars, evidence = load_causal_bar_window(
        bars_path,
        funding_paths,
        source_start,
        end,
        bar_timeframe="5min",
    )
    signals = build_impulse_signals(bars)
    scored_bars, scored_signals = scored_inputs(bars, signals, score_start)
    profiles = tuple(
        build_profile_report(
            profile,
            "long",
            evaluate_shared_bar_portfolio(
                scored_bars,
                scored_signals,
                portfolio_config(profile),
            ),
            profile_supported,
        )
        for profile in DEFAULT_PROFILES
    )
    return {
        "schema_version": 1,
        "mode": "v83_zec_corrected_hypertrader_impulse_report_only",
        "hypothesis_id": HYPOTHESIS_ID,
        "partition": partition,
        "source_start_utc": source_start.isoformat(),
        "start_utc": score_start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "execution_timeframe": "5min",
        "data_evidence": evidence,
        "signal_count": int(scored_signals["long_entry"].sum()),
        "profiles": list(profiles),
        "supported_in_partition": all(row["supported"] for row in profiles),
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _build_segment_signals(
    segment: pd.DataFrame,
    long_entry: pd.Series,
    stop_price: pd.Series,
) -> None:
    highs = segment["high"].astype(float).tolist()
    lows = segment["low"].astype(float).tolist()
    closes = segment["close"].astype(float).tolist()
    for position in range(_MINIMUM_INDICATOR_BARS - 1, len(segment)):
        start = max(0, position - _ROLLING_HISTORY_BARS + 1)
        window_highs = highs[start : position + 1]
        window_lows = lows[start : position + 1]
        window_closes = closes[start : position + 1]
        close = window_closes[-1]
        if not _entry_gate(window_highs, window_lows, window_closes):
            continue
        atr_pct = _atr_percent(window_highs, window_lows, window_closes)
        timestamp = segment.index[position]
        long_entry.loc[timestamp] = True
        stop_price.loc[timestamp] = close * (1.0 - atr_pct * _STOP_ATR_MULTIPLE / 100.0)


def _entry_gate(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> bool:
    ema = _ema_last(closes, _EMA_LENGTH)
    close_vs_ema = (closes[-1] - ema) / ema * 10_000.0
    di_delta = _directional_delta(highs, lows, closes)
    roc = (closes[-1] - closes[-6]) / closes[-6] * 100.0
    return bool(
        close_vs_ema <= _MAXIMUM_CLOSE_VS_EMA_BPS
        and di_delta <= _MAXIMUM_DI_DELTA
        and roc <= _MAXIMUM_ROC_5_PCT
    )


def _directional_delta(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> float:
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for position in range(1, len(closes)):
        up = highs[position] - highs[position - 1]
        down = lows[position - 1] - lows[position]
        plus_dm.append(up if up > down and up > 0.0 else 0.0)
        minus_dm.append(down if down > up and down > 0.0 else 0.0)
        true_ranges.append(_true_range(highs, lows, closes, position))
    atr = _wilder_last(true_ranges, _DIRECTIONAL_LENGTH)
    plus = _wilder_last(plus_dm, _DIRECTIONAL_LENGTH)
    minus = _wilder_last(minus_dm, _DIRECTIONAL_LENGTH)
    if atr <= 1e-12:
        return 0.0
    return 100.0 * (plus - minus) / atr


def _atr_percent(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> float:
    start = len(closes) - _ATR_LENGTH
    values = [
        _true_range(highs, lows, closes, position)
        for position in range(start, len(closes))
    ]
    return sum(values) / len(values) / closes[-1] * 100.0


def _true_range(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    position: int,
) -> float:
    prior_close = closes[position - 1]
    return max(
        highs[position] - lows[position],
        abs(highs[position] - prior_close),
        abs(lows[position] - prior_close),
    )


def _ema_last(values: list[float], length: int) -> float:
    current = sum(values[:length]) / length
    weight = 2.0 / (length + 1.0)
    for value in values[length:]:
        current = current * (1.0 - weight) + value * weight
    return current


def _wilder_last(values: list[float], length: int) -> float:
    current = sum(values[:length]) / length
    weight = 1.0 / length
    for value in values[length:]:
        current = current * (1.0 - weight) + value * weight
    return current


def _validate_bars(bars: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"impulse bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or not bars.index.is_unique:
        raise ValueError("impulse bars require a unique datetime index")
    if not bars.index.is_monotonic_increasing or len(bars) < 2:
        raise ValueError("impulse bars require at least two chronological rows")
    values = bars[list(required)].astype(float)
    if not values.map(math.isfinite).to_numpy().all():
        raise ValueError("impulse bars must be finite")


def _integer_metric(metrics: Mapping[str, object], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"profile metric {key} must be an integer")
    return value


def _float_metric(metrics: Mapping[str, object], key: str) -> float:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"profile metric {key} must be numeric")
    return float(value)


def _monthly_metrics(metrics: Mapping[str, object]) -> dict[str, float]:
    raw = metrics.get("monthly_net_pnl_usd")
    if not isinstance(raw, dict) or not raw:
        raise TypeError("profile monthly metrics must be a non-empty mapping")
    if any(not isinstance(key, str) for key in raw):
        raise TypeError("profile monthly metric keys must be strings")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw.values()
    ):
        raise TypeError("profile monthly metric values must be numeric")
    return {key: float(value) for key, value in raw.items()}
