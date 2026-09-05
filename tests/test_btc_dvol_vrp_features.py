"""Tests for causal BTC DVOL-versus-realized-volatility features."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from hypervector.research.btc_dvol_vrp_features import (
    build_btc_dvol_vrp_features,
)


def test_features_use_hour_close_availability_and_prior_return_window() -> None:
    """DVOL and BTC values become usable only after their labeled hour."""
    btc, dvol = _frames(900)

    features = build_btc_dvol_vrp_features(btc, dvol)

    assert features.iloc[0]["source_timestamp"] == btc.iloc[0]["timestamp"]
    assert features.iloc[0]["decision_time"] == (
        btc.iloc[0]["timestamp"] + pd.Timedelta(hours=1)
    )
    assert pd.isna(features.iloc[719]["realized_volatility"])
    expected_returns = np.log(btc["close"] / btc["close"].shift(1)).iloc[1:721]
    expected = expected_returns.std(ddof=0) * math.sqrt(24 * 365) * 100
    assert features.iloc[720]["realized_volatility"] == pytest.approx(expected)


def test_features_use_squared_fraction_units_and_exclude_current_threshold() -> None:
    """VRP units and rolling thresholds must match the frozen causal contract."""
    btc, dvol = _frames(3_000)
    dvol.loc[:, "close"] = np.linspace(40.0, 80.0, len(dvol))
    dvol.loc[:, "high"] = np.maximum(dvol["high"], dvol["close"])
    dvol.loc[:, "low"] = np.minimum(dvol["low"], dvol["close"])
    first = build_btc_dvol_vrp_features(btc, dvol)
    changed = dvol.copy()
    changed.loc[2_500, "close"] = 500.0
    changed.loc[2_500, "high"] = 500.0
    second = build_btc_dvol_vrp_features(btc, changed)

    row = first.iloc[2_500]
    expected_vrp = (row["dvol_close"] / 100) ** 2 - (
        row["realized_volatility"] / 100
    ) ** 2
    prior = first["vrp"].iloc[340:2_500]
    assert row["vrp"] == pytest.approx(expected_vrp)
    assert row["vrp_q75"] == pytest.approx(prior.quantile(0.75))
    assert second.iloc[2_500]["vrp_q75"] == pytest.approx(row["vrp_q75"])
    assert second.iloc[2_500]["vrp"] != pytest.approx(row["vrp"])


def test_features_shift_prior_high_and_compute_completed_close_emas() -> None:
    """Current prices cannot enter their own breakout reference window."""
    btc, dvol = _frames(300)
    btc.loc[:23, "high"] = np.arange(101.0, 125.0)
    btc.loc[24, ["high", "close"]] = [1_000.0, 200.0]

    features = build_btc_dvol_vrp_features(btc, dvol)

    assert features.iloc[24]["prior_24h_high"] == pytest.approx(124.0)
    assert features.iloc[24]["bullish_breakout"]
    expected_ema24 = btc["close"].ewm(span=24, adjust=False).mean().iloc[24]
    expected_ema168 = btc["close"].ewm(span=168, adjust=False).mean().iloc[24]
    assert features.iloc[24]["ema24"] == pytest.approx(expected_ema24)
    assert features.iloc[24]["ema168"] == pytest.approx(expected_ema168)


def test_future_extension_cannot_change_existing_features() -> None:
    """Appending extreme future values must leave the fitted prefix unchanged."""
    btc, dvol = _frames(3_000)
    prefix = build_btc_dvol_vrp_features(btc, dvol)
    later_btc, later_dvol = _frames(
        100, start=btc.iloc[-1]["timestamp"] + pd.Timedelta(hours=1)
    )
    later_btc.loc[:, ["open", "high", "low", "close"]] *= 20.0
    later_dvol.loc[:, ["open", "high", "low", "close"]] *= 10.0

    extended = build_btc_dvol_vrp_features(
        pd.concat([btc, later_btc], ignore_index=True),
        pd.concat([dvol, later_dvol], ignore_index=True),
    )

    pd.testing.assert_frame_equal(
        prefix, extended.iloc[: len(prefix)].reset_index(drop=True)
    )


def test_alignment_accepts_equal_utc_instants_with_different_storage_precision() -> (
    None
):
    """Parquet millisecond timestamps must align with microsecond BTC aggregation."""
    btc, dvol = _frames(900)
    dvol["timestamp"] = dvol["timestamp"].astype("datetime64[ms, UTC]")

    features = build_btc_dvol_vrp_features(btc, dvol)

    assert len(features) == 900
    assert pd.DatetimeIndex(features["source_timestamp"]).equals(
        pd.DatetimeIndex(dvol["timestamp"])
    )


@pytest.mark.parametrize(
    ("source", "mutation", "message"),
    [
        ("btc", "gap", "hourly continuity"),
        ("dvol", "gap", "hourly continuity"),
        ("btc", "na", "finite and positive"),
        ("dvol", "infinite", "finite and positive"),
        ("dvol", "offset", "aligned timestamps"),
        ("btc", "naive", "timezone-aware UTC"),
    ],
)
def test_features_fail_on_missing_invalid_or_misaligned_inputs(
    source: str,
    mutation: str,
    message: str,
) -> None:
    """The feature builder must not repair or forward-fill source defects."""
    btc, dvol = _frames(900)
    frame = btc if source == "btc" else dvol
    if mutation == "gap":
        frame.drop(index=100, inplace=True)
        frame.reset_index(drop=True, inplace=True)
    elif mutation == "na":
        frame.loc[100, "close"] = np.nan
    elif mutation == "infinite":
        frame.loc[100, "close"] = np.inf
    elif mutation == "offset":
        frame.loc[:, "timestamp"] += pd.Timedelta(hours=1)
    elif mutation == "naive":
        frame["timestamp"] = frame["timestamp"].dt.tz_localize(None)
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=message):
        build_btc_dvol_vrp_features(btc, dvol)


def _frames(
    rows: int,
    *,
    start: pd.Timestamp = pd.Timestamp("2025-07-28T00:00:00Z"),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamps = pd.date_range(start, periods=rows, freq="h")
    log_returns = np.where(np.arange(rows) % 2 == 0, 0.001, -0.0005)
    close = 100.0 * np.exp(np.cumsum(log_returns))
    btc = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
        }
    )
    dvol = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": np.full(rows, 60.0),
            "high": np.full(rows, 61.0),
            "low": np.full(rows, 59.0),
            "close": np.full(rows, 60.0),
        }
    )
    return btc, dvol
