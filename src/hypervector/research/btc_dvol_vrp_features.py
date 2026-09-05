"""Causal hourly BTC features for the preregistered DVOL-VRP experiment."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


_HOUR = pd.Timedelta(hours=1)
_RV_WINDOW = 720
_VRP_WINDOW = 2_160
_VRP_MINIMUM = 720
_BREAKOUT_WINDOW = 24
_FAST_EMA = 24
_SLOW_EMA = 168
_ANNUALIZATION = math.sqrt(24 * 365) * 100
_PRICE_COLUMNS = ("open", "high", "low", "close")


def build_btc_dvol_vrp_features(
    btc_hourly: pd.DataFrame,
    dvol_hourly: pd.DataFrame,
) -> pd.DataFrame:
    """Return ordered point-in-time BTC/DVOL features with no future fitting."""
    btc = _validated_hourly_frame(btc_hourly, "BTC")
    dvol = _validated_hourly_frame(dvol_hourly, "DVOL")
    _validate_alignment(btc, dvol)
    features = _base_features(btc, dvol)
    _add_realized_and_vrp(features)
    _add_causal_thresholds(features)
    _add_price_structure(features, btc)
    _add_states(features)
    return features


def _validated_hourly_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    required = {"timestamp", *_PRICE_COLUMNS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} hourly frame lacks columns: {missing}")
    validated = frame.loc[:, ["timestamp", *_PRICE_COLUMNS]].copy()
    timestamps = _validated_timestamps(validated["timestamp"], label)
    validated["timestamp"] = timestamps
    _validate_prices(validated, label)
    return validated.reset_index(drop=True)


def _validated_timestamps(values: pd.Series, label: str) -> pd.DatetimeIndex:
    try:
        timestamps = pd.DatetimeIndex(values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} timestamps are invalid") from exc
    if timestamps.tz is None or str(timestamps.tz) != "UTC":
        raise ValueError(f"{label} timestamps must be timezone-aware UTC")
    if timestamps.has_duplicates:
        raise ValueError(f"{label} timestamps contain duplicates")
    if not timestamps.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps are not ordered")
    differences = timestamps.to_series(index=range(len(timestamps))).diff().dropna()
    if not differences.eq(_HOUR).all():
        raise ValueError(f"{label} timestamps lack exact hourly continuity")
    return timestamps


def _validate_prices(frame: pd.DataFrame, label: str) -> None:
    numeric = frame.loc[:, _PRICE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError(f"{label} OHLC values must be finite and positive")
    invalid_high = numeric["high"] < numeric[["open", "low", "close"]].max(axis=1)
    invalid_low = numeric["low"] > numeric[["open", "high", "close"]].min(axis=1)
    if invalid_high.any() or invalid_low.any():
        raise ValueError(f"{label} OHLC bounds are invalid")
    frame.loc[:, _PRICE_COLUMNS] = numeric


def _validate_alignment(btc: pd.DataFrame, dvol: pd.DataFrame) -> None:
    btc_times = pd.DatetimeIndex(btc["timestamp"])
    dvol_times = pd.DatetimeIndex(dvol["timestamp"])
    if len(btc) != len(dvol) or not btc_times.equals(dvol_times):
        raise ValueError("BTC and DVOL require exactly aligned timestamps")


def _base_features(btc: pd.DataFrame, dvol: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_timestamp": btc["timestamp"],
            "decision_time": btc["timestamp"] + _HOUR,
            "btc_open": btc["open"].astype(float),
            "btc_high": btc["high"].astype(float),
            "btc_low": btc["low"].astype(float),
            "btc_close": btc["close"].astype(float),
            "dvol_close": dvol["close"].astype(float),
        }
    )


def _add_realized_and_vrp(features: pd.DataFrame) -> None:
    log_return = np.log(features["btc_close"] / features["btc_close"].shift(1))
    realized = log_return.rolling(_RV_WINDOW, min_periods=_RV_WINDOW).std(ddof=0)
    features["log_return"] = log_return
    features["realized_volatility"] = realized * _ANNUALIZATION
    implied_fraction = features["dvol_close"] / 100.0
    realized_fraction = features["realized_volatility"] / 100.0
    features["vrp"] = implied_fraction.pow(2) - realized_fraction.pow(2)


def _add_causal_thresholds(features: pd.DataFrame) -> None:
    prior = (
        features["vrp"]
        .shift(1)
        .rolling(
            _VRP_WINDOW,
            min_periods=_VRP_MINIMUM,
        )
    )
    features["vrp_q75"] = prior.quantile(0.75, interpolation="linear")
    features["vrp_median"] = prior.quantile(0.50, interpolation="linear")
    features["vrp_q25"] = prior.quantile(0.25, interpolation="linear")


def _add_price_structure(features: pd.DataFrame, btc: pd.DataFrame) -> None:
    prior_high = (
        btc["high"]
        .shift(1)
        .rolling(
            _BREAKOUT_WINDOW,
            min_periods=_BREAKOUT_WINDOW,
        )
        .max()
    )
    close = features["btc_close"]
    features["prior_24h_high"] = prior_high
    features["ema24"] = close.ewm(span=_FAST_EMA, adjust=False).mean()
    features["ema168"] = close.ewm(span=_SLOW_EMA, adjust=False).mean()
    features["bullish_breakout"] = close.gt(prior_high) & prior_high.notna()
    features["bullish_trend"] = close.gt(features["ema168"])
    features["bullish_structure"] = (
        features["bullish_breakout"] & features["bullish_trend"]
    )


def _add_states(features: pd.DataFrame) -> None:
    vrp = features["vrp"]
    features["high_vrp"] = vrp.ge(features["vrp_q75"]) & features["vrp_q75"].notna()
    features["low_vrp"] = vrp.le(features["vrp_q25"]) & features["vrp_q25"].notna()
