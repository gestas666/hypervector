"""Cost-derived causal clearance for HIP-3 pressure-breakout research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_breakout_pressure_transfer import (
    quote_aware_portfolio_config,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)

_REQUIRED_SIGNAL_COLUMNS = frozenset(
    (
        "prior_breakout_high",
        "prior_breakout_low",
        "fast_ema",
        "slow_ema",
        "decision_imbalance_10",
        "source_segment_id",
    )
)


@dataclass(frozen=True)
class Hip3BreakoutClearanceArm:
    """One fixed signal arm across development and validation windows."""

    development: SharedPortfolioReport
    development_folds: tuple[SharedPortfolioReport, ...]
    validation_nominal: SharedPortfolioReport
    validation_stress: SharedPortfolioReport


@dataclass(frozen=True)
class Hip3BreakoutClearanceResult:
    """Control and cost-clearance evidence without holdout access."""

    symbol: str
    config: Hip3BreakoutPressureConfig
    minimum_breakout_clearance_bps: float
    windows: Hip3TransferWindows
    control: Hip3BreakoutClearanceArm
    challenger: Hip3BreakoutClearanceArm
    holdout_status: str = "sealed_not_evaluated"
    execution_authority: str = "none"


def evaluate_breakout_cost_clearance(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    windows: Hip3TransferWindows,
    config: Hip3BreakoutPressureConfig,
    *,
    minimum_breakout_clearance_bps: float,
) -> Hip3BreakoutClearanceResult:
    """Evaluate one frozen SP500 clearance against its unchanged control."""
    clearance = _clearance(minimum_breakout_clearance_bps)
    _validate_windows(asset, windows)
    selected = _window(
        asset.bars, windows.development_start_utc, windows.validation_end_utc
    )
    bars = asset.bars.loc[selected].copy()
    control_signals = build_breakout_pressure_signals(bars, config)
    challenger_signals = build_breakout_cost_clearance_signals(
        bars,
        control_signals,
        config,
        minimum_breakout_clearance_bps=clearance,
    )
    nominal = quote_aware_portfolio_config(asset, friction, stress=False)
    stress = quote_aware_portfolio_config(asset, friction, stress=True)
    control = _evaluate_arm(bars, control_signals, windows, nominal, stress)
    challenger = _evaluate_arm(bars, challenger_signals, windows, nominal, stress)
    return Hip3BreakoutClearanceResult(
        asset.symbol, config, clearance, windows, control, challenger
    )


def breakout_cost_clearance_report(
    result: Hip3BreakoutClearanceResult,
) -> dict[str, object]:
    """Project a complete report while preserving the sealed holdout."""
    if result.holdout_status != "sealed_not_evaluated":
        raise ValueError("breakout cost-clearance holdout must remain sealed")
    return {
        "schema_version": "hip3_breakout_cost_clearance_v1",
        "contract": {
            "report_only": True,
            "execution_authority": result.execution_authority,
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "scope": {
            "symbol": result.symbol,
            "base_config": asdict(result.config),
            "minimum_breakout_clearance_bps": result.minimum_breakout_clearance_bps,
        },
        "windows": _window_report(result.windows),
        "arms": {
            "control": _arm_report(result.control),
            "challenger": _arm_report(result.challenger),
        },
        "holdout": {
            "status": result.holdout_status,
            "metrics_accessed": False,
            "start_utc": result.windows.validation_end_utc.isoformat(),
            "end_utc": result.windows.holdout_end_utc.isoformat(),
        },
    }


def build_breakout_cost_clearance_signals(
    bars: pd.DataFrame,
    control_signals: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
    *,
    minimum_breakout_clearance_bps: float,
    timeframe: str = "15m",
) -> pd.DataFrame:
    """Return fresh onsets after price clears the frozen cost threshold."""
    clearance = _clearance(minimum_breakout_clearance_bps)
    _validate_inputs(bars, control_signals, timeframe)
    prior_high = control_signals["prior_breakout_high"].astype(float)
    prior_low = control_signals["prior_breakout_low"].astype(float)
    fast = control_signals["fast_ema"].astype(float)
    slow = control_signals["slow_ema"].astype(float)
    pressure = control_signals["decision_imbalance_10"].astype(float)
    segments = control_signals["source_segment_id"].astype(int)
    fraction = clearance / 10_000.0
    long_raw = bars["close"].ge(prior_high * (1.0 + fraction))
    long_raw &= fast.gt(slow) & pressure.ge(config.minimum_abs_imbalance)
    short_raw = bars["close"].le(prior_low * (1.0 - fraction))
    short_raw &= fast.lt(slow) & pressure.le(-config.minimum_abs_imbalance)
    long_entry = _fresh_onset(long_raw, segments)
    short_entry = _fresh_onset(short_raw, segments)
    output = control_signals.copy()
    _assign_entries(output, long_entry, short_entry, timeframe)
    output["stop_price"] = _stop_prices(
        bars["close"], prior_high, prior_low, long_entry, short_entry, config
    )
    output["minimum_breakout_clearance_bps"] = clearance
    output["candidate_identity"] = "cost_derived_breakout_clearance"
    output["execution_authority"] = "none"
    return output


def _assign_entries(
    output: pd.DataFrame,
    long_entry: pd.Series,
    short_entry: pd.Series,
    timeframe: str,
) -> None:
    """Replace control entries with challenger identities in-place."""
    direction = pd.Series([None] * len(output), index=output.index, dtype=object)
    direction.loc[long_entry] = "long"
    direction.loc[short_entry] = "short"
    names = pd.Series([None] * len(output), index=output.index, dtype=object)
    names.loc[long_entry] = f"hip3_breakout_cost_clearance_long@{timeframe}"
    names.loc[short_entry] = f"hip3_breakout_cost_clearance_short@{timeframe}"
    output["long_entry"] = long_entry.astype(bool)
    output["short_entry"] = short_entry.astype(bool)
    output["entry_direction"] = direction
    output["breakout_side"] = direction.copy()
    output["signal_name"] = names


def _stop_prices(
    close: pd.Series,
    prior_high: pd.Series,
    prior_low: pd.Series,
    long_entry: pd.Series,
    short_entry: pd.Series,
    config: Hip3BreakoutPressureConfig,
) -> pd.Series:
    """Return the unchanged base structural/fixed stop at challenger onset."""
    stop_fraction = config.maximum_stop_bps / 10_000.0
    stops = pd.Series(float("nan"), index=close.index, dtype=float)
    fixed_long = close.astype(float) * (1.0 - stop_fraction)
    fixed_short = close.astype(float) * (1.0 + stop_fraction)
    stops.loc[long_entry] = pd.concat([fixed_long, prior_low], axis=1).max(axis=1)
    stops.loc[short_entry] = pd.concat([fixed_short, prior_high], axis=1).min(axis=1)
    return stops


def _fresh_onset(raw: pd.Series, segments: pd.Series) -> pd.Series:
    """Return the first true row in each contiguous segmented condition."""
    prior = raw.groupby(segments, sort=False).shift(1, fill_value=False)
    return raw.fillna(False) & ~prior.astype(bool)


def _clearance(value: float) -> float:
    """Validate and return the strictly positive frozen clearance."""
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("minimum breakout clearance must be finite and positive")
    return float(value)


def _validate_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    timeframe: str,
) -> None:
    """Reject misaligned or incomplete control evidence."""
    if timeframe not in {"5m", "15m"}:
        raise ValueError("clearance timeframe must be 5m or 15m")
    if not bars.index.equals(signals.index):
        raise ValueError("clearance bars and control signal index must match")
    missing = _REQUIRED_SIGNAL_COLUMNS.difference(signals.columns)
    if missing:
        raise ValueError(f"clearance control signals missing: {sorted(missing)}")
    if "close" not in bars.columns:
        raise ValueError("clearance bars missing close")


def _evaluate_arm(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    windows: Hip3TransferWindows,
    nominal: SharedPortfolioConfig,
    stress: SharedPortfolioConfig,
) -> Hip3BreakoutClearanceArm:
    """Evaluate one frozen signal arm without entering the holdout."""
    development = _evaluate_window(
        bars,
        signals,
        windows.development_start_utc,
        windows.development_end_utc,
        nominal,
    )
    folds = tuple(
        _evaluate_window(bars, signals, start, end, nominal)
        for start, end in windows.development_folds
    )
    validation_nominal = _evaluate_window(
        bars, signals, windows.development_end_utc, windows.validation_end_utc, nominal
    )
    validation_stress = _evaluate_window(
        bars, signals, windows.development_end_utc, windows.validation_end_utc, stress
    )
    return Hip3BreakoutClearanceArm(
        development, folds, validation_nominal, validation_stress
    )


def _evaluate_window(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: SharedPortfolioConfig,
) -> SharedPortfolioReport:
    """Evaluate one half-open chronological window."""
    selected = _window(bars, start, end)
    return evaluate_shared_bar_portfolio(
        bars.loc[selected].copy(),
        signals.loc[selected].copy(),
        config,
    )


def _window(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Return a half-open timestamp mask for one evidence window."""
    return bars.index.to_series().ge(start) & bars.index.to_series().lt(end)


def _validate_windows(asset: Hip3TransferAsset, windows: Hip3TransferWindows) -> None:
    """Require complete declared coverage without synthesizing bars."""
    observed_start = asset.bars.index.min()
    observed_end = asset.bars.index.max() + pd.Timedelta(minutes=15)
    ordered = (
        observed_start
        <= windows.development_start_utc
        < windows.development_end_utc
        < windows.validation_end_utc
        < windows.holdout_end_utc
        <= observed_end
    )
    if not ordered or len(windows.development_folds) != 3:
        raise ValueError("breakout cost-clearance window is incomplete or invalid")


def _arm_report(arm: Hip3BreakoutClearanceArm) -> dict[str, object]:
    """Project every chronological cell for one arm."""
    return {
        "development": _summary(arm.development),
        "development_folds": [_summary(report) for report in arm.development_folds],
        "validation_nominal": _summary(arm.validation_nominal),
        "validation_stress": _summary(arm.validation_stress),
    }


def _summary(report: SharedPortfolioReport) -> dict[str, object]:
    """Return side-aware economics and largest-winner sensitivity."""
    side_count = {"long": 0, "short": 0}
    side_net = {"long": 0.0, "short": 0.0}
    for trade in report.trades:
        side_count[trade.direction] += 1
        side_net[trade.direction] += trade.net_pnl_usd
    winners = [trade.net_pnl_usd for trade in report.trades if trade.net_pnl_usd > 0.0]
    largest = max(winners, default=None)
    without_largest = (
        report.net_pnl_usd - largest if largest is not None else report.net_pnl_usd
    )
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_pnl_usd": report.net_pnl_usd,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "liquidations": report.liquidations,
        "barrier_invalidated_entries": report.barrier_invalidated_entries,
        "direction_trades": side_count,
        "direction_net_pnl_usd": side_net,
        "largest_winner_usd": largest,
        "net_pnl_excluding_largest_winner_usd": without_largest,
    }


def _window_report(windows: Hip3TransferWindows) -> dict[str, object]:
    """Return the exact declared chronological boundary."""
    return {
        "development_start_utc": windows.development_start_utc.isoformat(),
        "development_end_utc": windows.development_end_utc.isoformat(),
        "validation_end_utc": windows.validation_end_utc.isoformat(),
        "holdout_end_utc": windows.holdout_end_utc.isoformat(),
        "development_folds": [
            {"start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for start, end in windows.development_folds
        ],
    }
