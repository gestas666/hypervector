"""Causal completed-bar cross-asset residual states and entry onsets."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualSignal,
)

_STATE_COLUMNS = {
    "bar_open_at",
    "decision_time_utc",
    "left_symbol",
    "right_symbol",
    "hedge_ratio",
    "intercept",
    "residual",
    "residual_mean",
    "residual_std",
    "zscore",
    "error_correction_t",
    "fit_start_utc",
    "fit_end_utc",
    "stationarity_admitted",
}


@dataclass(frozen=True)
class _ResidualFit:
    """One point-in-time OLS and residual mean-reversion estimate."""

    intercept: float
    hedge_ratio: float
    error_correction_t: float
    start: pd.Timestamp
    end: pd.Timestamp


def build_residual_states(
    left_close: pd.Series,
    right_close: pd.Series,
    left_symbol: str,
    right_symbol: str,
    config: CrossAssetResidualConfig | None = None,
) -> pd.DataFrame:
    """Return point-in-time residual states for one ordered asset pair."""
    cfg = config or CrossAssetResidualConfig()
    left, right = _validated_prices(left_close, right_close, left_symbol, right_symbol)
    log_left = np.log(left.to_numpy(dtype=float))
    log_right = np.log(right.to_numpy(dtype=float))
    rows: list[dict[str, object]] = []
    fit: _ResidualFit | None = None
    for position, timestamp in enumerate(left.index):
        if _must_refit(position, fit, cfg):
            fit = _fit_trailing(log_left, log_right, left.index, position, cfg)
        rows.append(
            _state_row(
                position,
                timestamp,
                log_left,
                log_right,
                left_symbol,
                right_symbol,
                fit,
                cfg,
            )
        )
    return pd.DataFrame.from_records(rows)


def build_residual_signals(
    states: pd.DataFrame,
    config: CrossAssetResidualConfig | None = None,
) -> tuple[ResidualSignal, ...]:
    """Return onset-only long- and short-spread entry signals."""
    cfg = config or CrossAssetResidualConfig()
    missing = sorted(_STATE_COLUMNS.difference(states.columns))
    if missing:
        raise ValueError(f"residual states missing columns: {missing}")
    admitted = states["stationarity_admitted"].fillna(False).astype(bool)
    zscore = states["zscore"].astype(float)
    ready = {
        "long_spread": admitted & zscore.le(-cfg.entry_z),
        "short_spread": admitted & zscore.ge(cfg.entry_z),
    }
    signals: list[ResidualSignal] = []
    for direction, mask in ready.items():
        onset = mask & ~mask.shift(1, fill_value=False)
        signals.extend(
            _signal(states.iloc[position], direction)
            for position in np.flatnonzero(onset.to_numpy())
        )
    return tuple(sorted(signals, key=lambda value: value.decision_time_utc))


def _validated_prices(
    left: pd.Series,
    right: pd.Series,
    left_symbol: str,
    right_symbol: str,
) -> tuple[pd.Series, pd.Series]:
    if not left_symbol or not right_symbol or left_symbol == right_symbol:
        raise ValueError("residual pair requires two distinct symbols")
    if left_symbol != left_symbol.upper() or right_symbol != right_symbol.upper():
        raise ValueError("residual symbols must be uppercase")
    if left.empty or not left.index.equals(right.index):
        raise ValueError("residual price series must have aligned non-empty indexes")
    index = pd.DatetimeIndex(left.index)
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("residual prices require an ordered unique aware index")
    if len(index) > 1 and not (index[1:] - index[:-1] == pd.Timedelta(minutes=5)).all():
        raise ValueError("residual prices require complete five-minute spacing")
    values = np.column_stack((left.to_numpy(float), right.to_numpy(float)))
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("residual prices must be positive and finite")
    return left.astype(float), right.astype(float)


def _must_refit(
    position: int,
    fit: _ResidualFit | None,
    config: CrossAssetResidualConfig,
) -> bool:
    if position < config.lookback_bars:
        return False
    return (
        fit is None
        or (position - config.lookback_bars) % config.refit_interval_bars == 0
    )


def _fit_trailing(
    left: np.ndarray,
    right: np.ndarray,
    index: pd.DatetimeIndex,
    position: int,
    config: CrossAssetResidualConfig,
) -> _ResidualFit:
    start = position - config.lookback_bars
    x = right[start:position]
    y = left[start:position]
    design = np.column_stack((np.ones(len(x)), x))
    intercept, hedge = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - intercept - hedge * x
    error_t = _error_correction_t(residual)
    fit_end = index[position - 1] + pd.Timedelta(minutes=5)
    return _ResidualFit(float(intercept), float(hedge), error_t, index[start], fit_end)


def _error_correction_t(residual: np.ndarray) -> float:
    lagged = residual[:-1]
    change = np.diff(residual)
    design = np.column_stack((np.ones(len(lagged)), lagged))
    coefficients = np.linalg.lstsq(design, change, rcond=None)[0]
    errors = change - design @ coefficients
    degrees = len(change) - design.shape[1]
    inverse = np.linalg.pinv(design.T @ design)
    variance = float(errors @ errors) / degrees if degrees > 0 else math.nan
    standard_error = math.sqrt(max(0.0, variance * float(inverse[1, 1])))
    return float(coefficients[1] / standard_error) if standard_error > 0.0 else math.nan


def _state_row(
    position: int,
    timestamp: pd.Timestamp,
    left: np.ndarray,
    right: np.ndarray,
    left_symbol: str,
    right_symbol: str,
    fit: _ResidualFit | None,
    config: CrossAssetResidualConfig,
) -> dict[str, object]:
    base = _empty_state(timestamp, left_symbol, right_symbol)
    if fit is None or position < config.zscore_window_bars:
        return base
    start = position - config.zscore_window_bars
    history = (
        left[start:position] - fit.intercept - fit.hedge_ratio * right[start:position]
    )
    mean = float(np.mean(history))
    standard = float(np.std(history, ddof=1))
    residual = float(left[position] - fit.intercept - fit.hedge_ratio * right[position])
    zscore = (residual - mean) / standard if standard > 0.0 else math.nan
    admitted = _stationarity_admitted(fit.error_correction_t, config)
    base.update(
        hedge_ratio=fit.hedge_ratio,
        intercept=fit.intercept,
        residual=residual,
        residual_mean=mean,
        residual_std=standard,
        zscore=zscore,
        error_correction_t=fit.error_correction_t,
        fit_start_utc=fit.start.isoformat(),
        fit_end_utc=fit.end.isoformat(),
        stationarity_admitted=admitted,
    )
    return base


def _empty_state(
    timestamp: pd.Timestamp,
    left_symbol: str,
    right_symbol: str,
) -> dict[str, object]:
    return {
        "bar_open_at": timestamp,
        "decision_time_utc": (timestamp + pd.Timedelta(minutes=5)).isoformat(),
        "left_symbol": left_symbol,
        "right_symbol": right_symbol,
        "hedge_ratio": math.nan,
        "intercept": math.nan,
        "residual": math.nan,
        "residual_mean": math.nan,
        "residual_std": math.nan,
        "zscore": math.nan,
        "error_correction_t": math.nan,
        "fit_start_utc": None,
        "fit_end_utc": None,
        "stationarity_admitted": False,
    }


def _stationarity_admitted(
    error_t: float,
    config: CrossAssetResidualConfig,
) -> bool:
    if not math.isfinite(error_t):
        return False
    threshold = config.minimum_abs_error_correction_t
    return threshold == 0.0 or error_t <= -threshold


def _signal(row: pd.Series, direction: str) -> ResidualSignal:
    if direction not in {"long_spread", "short_spread"}:
        raise ValueError("residual signal direction is invalid")
    return ResidualSignal(
        decision_time_utc=str(row["decision_time_utc"]),
        left_symbol=str(row["left_symbol"]),
        right_symbol=str(row["right_symbol"]),
        direction=direction,
        hedge_ratio=float(row["hedge_ratio"]),
        intercept=float(row["intercept"]),
        residual=float(row["residual"]),
        residual_mean=float(row["residual_mean"]),
        residual_std=float(row["residual_std"]),
        zscore=float(row["zscore"]),
        error_correction_t=float(row["error_correction_t"]),
        fit_start_utc=str(row["fit_start_utc"]),
        fit_end_utc=str(row["fit_end_utc"]),
        execution_authority="none",
    )
