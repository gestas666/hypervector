"""Preregistered ZEC UT-Bot peak-harvest transfer research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import math
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.causal_screen_inputs import load_causal_bar_window
from hypervector.research.completed_bar_indicators import (
    complete_resampled_ohlc,
    contiguous_segment_ids,
    raw_true_range,
    segmented_wilder_rma,
    validated_ohlc_bars,
)
from hypervector.research.fixed_risk_signal_screen import (
    DEFAULT_PROFILES,
    FrictionProfile,
    scored_inputs,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_attribution import trade_attribution
from hypervector.research.shared_portfolio_completed_peak_lock import (
    CompletedBarPeakLockPolicy,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)

HYPOTHESIS_ID = "v86-zec-utbot-peak-harvest-transfer-20260904"
STRATEGY_ID = "zec_utbot_ha4h_atr13_peak80_bidirectional_v1"
SHORT_STRATEGY_ID = "zec_utbot_ha4h_atr13_peak80_short_v1"
MINIMUM_COMPLETED_TRADES = 15
MAXIMUM_DRAWDOWN_PCT = 5.0


@dataclass(frozen=True)
class UtBotPeakHarvestConfig:
    """Exact authority-none parameters frozen before ZEC replay."""

    key_value: float = 1.0
    atr_period: int = 13
    signal_hours: int = 4
    execution_minutes: int = 15
    activation_roe_pct: float = 10.0
    locked_peak_ratio: float = 0.8
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject signal, exit, clock, or authority drift."""
        values = (
            self.key_value,
            self.atr_period,
            self.signal_hours,
            self.execution_minutes,
            self.activation_roe_pct,
            self.locked_peak_ratio,
        )
        if values != (1.0, 13, 4, 15, 10.0, 0.8):
            raise ValueError("ZEC UT-Bot parameters must remain frozen")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("ZEC UT-Bot research must remain report-only")


def build_utbot_state(
    signal_bars: pd.DataFrame,
    config: UtBotPeakHarvestConfig | None = None,
) -> pd.DataFrame:
    """Return causal regular-ATR and Heikin-Ashi UT-stop crossings."""
    cfg = config or UtBotPeakHarvestConfig()
    frame = validated_ohlc_bars(signal_bars, label="ZEC UT-Bot")
    segments = contiguous_segment_ids(
        frame.index,
        pd.Timedelta(hours=cfg.signal_hours),
    )
    atr = segmented_wilder_rma(
        raw_true_range(frame, segments),
        segments,
        cfg.atr_period,
    )
    source = _heikin_ashi_close(frame)
    stop = _recursive_stop(source, atr * cfg.key_value, segments)
    long_entry, short_entry = _crossings(source, stop, segments)
    return pd.DataFrame(
        {
            "ha_close": source,
            "atr": atr,
            "ut_stop": stop,
            "long_entry": long_entry,
            "short_entry": short_entry,
        },
        index=frame.index,
    )


def build_utbot_signals(
    execution_bars: pd.DataFrame,
    config: UtBotPeakHarvestConfig | None = None,
) -> pd.DataFrame:
    """Project completed four-hour crossings for next-15-minute-open entry."""
    cfg = config or UtBotPeakHarvestConfig()
    frame = validated_ohlc_bars(execution_bars, label="ZEC UT-Bot")
    signal_bars = complete_resampled_ohlc(
        frame,
        source_minutes=cfg.execution_minutes,
        target_hours=cfg.signal_hours,
    )
    state = build_utbot_state(signal_bars, cfg)
    output = _empty_signals(frame.index)
    _project_state(output, state, cfg)
    return output


def build_utbot_short_signals(
    execution_bars: pd.DataFrame,
    config: UtBotPeakHarvestConfig | None = None,
) -> pd.DataFrame:
    """Retain only short entries while preserving upward-crossing exits."""
    output = build_utbot_signals(execution_bars, config)
    output["long_entry"] = False
    output["long_signal_name"] = "inactive_long"
    output["short_signal_name"] = SHORT_STRATEGY_ID
    return output


def portfolio_config(profile: FrictionProfile) -> SharedPortfolioConfig:
    """Return the frozen probation risk, cost, and peak-harvest contract."""
    return SharedPortfolioConfig(
        symbol="ZEC",
        initial_equity=5_000.0,
        margin_fraction=0.02,
        leverage=5.0,
        venue_max_leverage=10.0,
        maximum_notional_usd=500.0,
        risk_fraction_per_position=0.005,
        stop_margin_pct=20.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=profile.slippage_bps,
        market_exit_slippage_bps=profile.slippage_bps,
        max_hold_seconds=2_592_000,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=True,
        completed_bar_peak_lock=CompletedBarPeakLockPolicy(
            "zec_utbot_completed15_peak80_v1",
            activation_roe_pct=10.0,
            locked_peak_ratio=0.8,
        ),
    )


def short_portfolio_config(profile: FrictionProfile) -> SharedPortfolioConfig:
    """Disable reversal into the rejected long sleeve without changing risk."""
    return replace(portfolio_config(profile), reverse_on_opposite_signal=False)


def profile_supported(metrics: Mapping[str, object]) -> bool:
    """Apply every frozen per-profile support criterion."""
    completed = _integer_metric(metrics, "completed_trades")
    net = _float_metric(metrics, "net_pnl_usd")
    raw_factor = metrics.get("profit_factor")
    factor = None if raw_factor is None else _float_metric(metrics, "profit_factor")
    ex_largest = _float_metric(metrics, "net_excluding_largest_winner_usd")
    drawdown = _float_metric(metrics, "maximum_drawdown_pct")
    liquidations = _integer_metric(metrics, "liquidations")
    insolvent = metrics.get("insolvent")
    if not isinstance(insolvent, bool):
        raise TypeError("profile metric insolvent must be a boolean")
    monthly = _monthly_metrics(metrics)
    positive_fraction = sum(value > 0.0 for value in monthly.values()) / len(monthly)
    return bool(
        completed >= MINIMUM_COMPLETED_TRADES
        and net > 0.0
        and factor is not None
        and factor > 1.0
        and ex_largest > 0.0
        and drawdown >= -MAXIMUM_DRAWDOWN_PCT
        and positive_fraction >= 0.5
        and liquidations == 0
        and not insolvent
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
    """Evaluate one opened chronological partition without authority."""
    return _run_partition(
        bars_path=bars_path,
        funding_paths=funding_paths,
        source_start=source_start,
        score_start=score_start,
        end=end,
        partition=partition,
        short_only=False,
    )


def run_short_partition_screen(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
) -> dict[str, object]:
    """Evaluate the disclosed short-only sleeve without authority."""
    return _run_partition(
        bars_path=bars_path,
        funding_paths=funding_paths,
        source_start=source_start,
        score_start=score_start,
        end=end,
        partition=partition,
        short_only=True,
    )


def _run_partition(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
    short_only: bool,
) -> dict[str, object]:
    bars, evidence = load_causal_bar_window(
        bars_path,
        funding_paths,
        source_start,
        end,
        bar_timeframe="15min",
    )
    signal_builder = build_utbot_short_signals if short_only else build_utbot_signals
    config_builder = short_portfolio_config if short_only else portfolio_config
    signals = signal_builder(bars)
    scored_bars, scored_signals = scored_inputs(bars, signals, score_start)
    profiles = tuple(
        _profile_report(
            profile,
            evaluate_shared_bar_portfolio(
                scored_bars,
                scored_signals,
                config_builder(profile),
            ),
        )
        for profile in DEFAULT_PROFILES
    )
    return {
        "schema_version": 1,
        "mode": (
            "v86_zec_utbot_short_peak_harvest_report_only"
            if short_only
            else "v86_zec_utbot_peak_harvest_report_only"
        ),
        "hypothesis_id": HYPOTHESIS_ID,
        "partition": partition,
        "source_start_utc": source_start.isoformat(),
        "start_utc": score_start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "execution_timeframe": "15min",
        "data_evidence": evidence,
        "signal_counts": {
            "long": int(scored_signals["long_entry"].sum()),
            "short": int(scored_signals["short_entry"].sum()),
        },
        "profiles": list(profiles),
        "supported_in_partition": all(row["supported"] for row in profiles),
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _heikin_ashi_close(frame: pd.DataFrame) -> NDArray[np.float64]:
    values = frame.loc[:, ["open", "high", "low", "close"]].to_numpy(dtype=np.float64)
    return values.mean(axis=1)


def _recursive_stop(
    source: NDArray[np.float64],
    loss: NDArray[np.float64],
    segments: NDArray[np.int64],
) -> NDArray[np.float64]:
    stop = np.full(len(source), np.nan, dtype=np.float64)
    for position in range(len(source)):
        if not math.isfinite(float(loss[position])):
            continue
        same = position > 0 and segments[position] == segments[position - 1]
        candidate = stop[position - 1] if same else math.nan
        prior_stop = float(candidate) if math.isfinite(float(candidate)) else 0.0
        prior_source = source[position - 1] if same else math.nan
        stop[position] = _next_stop(
            float(source[position]),
            float(prior_source),
            float(prior_stop),
            float(loss[position]),
        )
    return stop


def _next_stop(source: float, prior_source: float, prior: float, loss: float) -> float:
    if source > prior and math.isfinite(prior_source) and prior_source > prior:
        return max(prior, source - loss)
    if source < prior and math.isfinite(prior_source) and prior_source < prior:
        return min(prior, source + loss)
    return source - loss if source > prior else source + loss


def _crossings(
    source: NDArray[np.float64],
    stop: NDArray[np.float64],
    segments: NDArray[np.int64],
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    long_entry = np.zeros(len(source), dtype=np.bool_)
    short_entry = np.zeros(len(source), dtype=np.bool_)
    for position in range(1, len(source)):
        same = segments[position] == segments[position - 1]
        ready = math.isfinite(float(stop[position - 1])) and math.isfinite(
            float(stop[position])
        )
        if not same or not ready:
            continue
        long_entry[position] = (
            source[position] > stop[position]
            and source[position - 1] <= stop[position - 1]
        )
        short_entry[position] = (
            source[position] < stop[position]
            and source[position - 1] >= stop[position - 1]
        )
    return long_entry, short_entry


def _empty_signals(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "long_entry": False,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "long_signal_name": STRATEGY_ID,
            "short_signal_name": STRATEGY_ID,
            "ha_close": np.nan,
            "atr": np.nan,
            "ut_stop": np.nan,
        },
        index=index,
    )


def _project_state(
    output: pd.DataFrame,
    state: pd.DataFrame,
    config: UtBotPeakHarvestConfig,
) -> None:
    for signal_time, row in state.iterrows():
        decision = (
            pd.Timestamp(signal_time)
            + pd.Timedelta(hours=config.signal_hours)
            - pd.Timedelta(minutes=config.execution_minutes)
        )
        if decision not in output.index:
            raise RuntimeError("completed ZEC UT-Bot bar lacks its decision row")
        output.loc[decision, ["ha_close", "atr", "ut_stop"]] = row[
            ["ha_close", "atr", "ut_stop"]
        ].to_numpy()
        if bool(row["long_entry"]):
            output.loc[decision, ["long_entry", "short_exit"]] = True
        if bool(row["short_entry"]):
            output.loc[decision, ["short_entry", "long_exit"]] = True


def _profile_report(
    profile: FrictionProfile,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    values = report.to_dict()
    attribution = trade_attribution(report.trades)
    largest = max(
        float(attribution[side]["largest_winner_usd"] or 0.0)
        for side in ("long", "short")
    )
    metrics = {
        key: values[key]
        for key in (
            "completed_trades",
            "wins",
            "losses",
            "net_pnl_usd",
            "profit_factor",
            "maximum_drawdown_pct",
            "liquidations",
            "total_fees_usd",
            "funding_cashflow_usd",
            "insolvent",
            "monthly_net_pnl_usd",
        )
    }
    metrics["net_excluding_largest_winner_usd"] = report.net_pnl_usd - largest
    return {
        "friction": asdict(profile),
        "metrics": metrics,
        "attribution": attribution,
        "supported": profile_supported(metrics),
    }


def _monthly_metrics(metrics: Mapping[str, object]) -> dict[str, float]:
    value = metrics.get("monthly_net_pnl_usd")
    if not isinstance(value, dict) or not value:
        raise TypeError("profile monthly metrics must be a non-empty mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("profile monthly metric keys must be text")
    output = {key: _numeric(raw, "monthly PnL") for key, raw in value.items()}
    return output


def _integer_metric(metrics: Mapping[str, object], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"profile metric {key} must be an integer")
    return value


def _float_metric(metrics: Mapping[str, object], key: str) -> float:
    return _numeric(metrics.get(key), f"profile metric {key}")


def _numeric(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number
