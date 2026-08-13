"""Development-only HIP-3 candle-source sensitivity diagnostics."""

from __future__ import annotations

from dataclasses import asdict
import math

import pandas as pd

from hypervector.research.hip3_archive_inputs import (
    build_archive_breakout_signals,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveExecution,
    mu_archive_portfolio_config,
)
from hypervector.research.mu_hip3_archive_reporting import report_summary
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioReport

_SIGNAL_FIELDS = ("long_entry", "short_entry", "long_exit", "short_exit")


def build_hip3_signal_source_sensitivity(
    *,
    bars: pd.DataFrame,
    venue_ohlc: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
    execution: MuArchiveExecution,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> dict[str, object]:
    """Compare one frozen route under two signal OHLC sources."""
    start, end = _validated_bounds(start_utc, end_utc)
    scoped_bars, scoped_venue = _aligned_inputs(bars, venue_ohlc, start, end)
    trade_signals = build_archive_breakout_signals(scoped_bars, config, "15m")
    venue_bars = _with_venue_source(scoped_bars, scoped_venue)
    venue_signals = build_archive_breakout_signals(venue_bars, config, "15m")
    trade_reports = _reports(scoped_bars, trade_signals, execution)
    venue_reports = _reports(scoped_bars, venue_signals, execution)
    comparison = _signal_comparison(trade_signals, venue_signals)
    return _report(
        config,
        execution,
        start,
        end,
        scoped_bars,
        comparison,
        trade_reports,
        venue_reports,
    )


def _validated_bounds(
    start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("signal-source sensitivity requires ordered UTC bounds")
    if start.floor("15min") != start or end.floor("15min") != end:
        raise ValueError("signal-source sensitivity bounds must be 15m aligned")
    return start, end


def _aligned_inputs(
    bars: pd.DataFrame,
    venue: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _validate_index(bars, "archive")
    _validate_index(venue, "venue")
    archive = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    candles = venue.loc[(venue.index >= start) & (venue.index < end)].copy()
    if archive.empty or not archive.index.equals(candles.index):
        raise ValueError("venue candle indexes must exactly match archive bars")
    expected = pd.date_range(start, end, freq="15min", inclusive="left")
    if not archive.index.equals(expected):
        raise ValueError("signal-source sensitivity requires contiguous 15m bars")
    if len(archive) <= 1:
        raise ValueError("signal-source sensitivity requires multiple bars")
    return archive, _validated_ohlc(candles)


def _validate_index(frame: pd.DataFrame, label: str) -> None:
    index = frame.index
    invalid = (
        not isinstance(index, pd.DatetimeIndex)
        or index.tz is None
        or not index.is_monotonic_increasing
        or not index.is_unique
    )
    if invalid:
        raise ValueError(f"{label} bars require ordered unique UTC timestamps")


def _validated_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["open", "high", "low", "close"]
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise ValueError(f"venue candles missing OHLC columns: {missing}")
    output = frame.loc[:, required].astype(float).copy()
    if not output.map(math.isfinite).to_numpy().all() or output.le(0).any().any():
        raise ValueError("venue candle OHLC must be finite and positive")
    if output["high"].lt(output[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("venue candle highs are inconsistent")
    if output["low"].gt(output[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("venue candle lows are inconsistent")
    return output


def _with_venue_source(bars: pd.DataFrame, venue: pd.DataFrame) -> pd.DataFrame:
    output = bars.copy()
    for name in ("open", "high", "low", "close"):
        output[f"signal_{name}"] = venue[name]
    return output


def _reports(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    execution: MuArchiveExecution,
) -> dict[str, SharedPortfolioReport]:
    return {
        label: evaluate_shared_bar_portfolio(
            bars,
            signals,
            mu_archive_portfolio_config(
                execution, family="breakout_pressure", stress=stress
            ),
        )
        for label, stress in (("nominal", False), ("stress", True))
    }


def _signal_comparison(trade: pd.DataFrame, venue: pd.DataFrame) -> dict[str, object]:
    differences = {name: trade[name].ne(venue[name]) for name in _SIGNAL_FIELDS}
    entry = differences["long_entry"] | differences["short_entry"]
    exit_signal = differences["long_exit"] | differences["short_exit"]
    union = pd.concat(differences.values(), axis=1).any(axis=1)
    return {
        "entry_disagreement_bars": int(entry.sum()),
        "exit_disagreement_bars": int(exit_signal.sum()),
        "any_signal_disagreement_bars": int(union.sum()),
        "disagreement_rows": _disagreement_rows(differences, union),
        "public_trade_entry_bars": int(
            (trade["long_entry"] | trade["short_entry"]).sum()
        ),
        "venue_candle_entry_bars": int(
            (venue["long_entry"] | venue["short_entry"]).sum()
        ),
    }


def _disagreement_rows(
    differences: dict[str, pd.Series], union: pd.Series
) -> list[dict[str, object]]:
    return [
        {
            "timestamp_utc": pd.Timestamp(timestamp).isoformat(),
            "fields": [
                name for name in _SIGNAL_FIELDS if differences[name].loc[timestamp]
            ],
        }
        for timestamp in union.index[union]
    ]


def _report(
    config: Hip3BreakoutPressureConfig,
    execution: MuArchiveExecution,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bars: pd.DataFrame,
    comparison: dict[str, object],
    trade: dict[str, SharedPortfolioReport],
    venue: dict[str, SharedPortfolioReport],
) -> dict[str, object]:
    trade_values = _report_values(trade, start, end, execution.symbol)
    venue_values = _report_values(venue, start, end, execution.symbol)
    economic_delta = {
        scenario: venue[scenario].net_pnl_usd - trade[scenario].net_pnl_usd
        for scenario in ("nominal", "stress")
    }
    return {
        "schema_version": "hip3_signal_source_sensitivity_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "out_of_sample_evaluated": False,
            "runtime_strategy_changed": False,
        },
        "symbol": execution.symbol,
        "timeframe": "15m",
        "config": asdict(config),
        "window": {"start_utc": start.isoformat(), "end_utc": end.isoformat()},
        "coverage": {"bars": len(bars), "contiguous": True},
        "signal_comparison": comparison,
        "public_trade_source": trade_values,
        "venue_candle_source": venue_values,
        "venue_minus_public_trade_net_pnl_usd": economic_delta,
        "source_invariant": not comparison["any_signal_disagreement_bars"]
        and all(value == 0.0 for value in economic_delta.values()),
    }


def _report_values(
    reports: dict[str, SharedPortfolioReport],
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol: str,
) -> dict[str, object]:
    return {
        name: report_summary(value, start, end, symbol=symbol)
        for name, value in reports.items()
    }
