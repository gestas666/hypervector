"""Frozen 15-minute feature and 30-minute continuation-label research contract."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES = ("return_1", "return_3", "return_6", "return_12", "atr_20",
                 "volatility_12", "distance_sma_21", "distance_sma_55")
BAR_INTERVAL = pd.Timedelta(minutes=15)
LABEL_HORIZON_BARS = 2
FEATURE_WINDOW_BARS = 55


def continuation_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Construct causal bps features, refusing malformed or unordered OHLC."""
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("continuation bars require a timezone-aware DatetimeIndex")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("continuation timestamps must be unique and ordered")
    prices = bars.loc[:, ["open", "high", "low", "close"]]
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("continuation OHLC must be finite positive")
    if ((prices.high < prices[["open", "close", "low"]].max(axis=1)) |
            (prices.low > prices[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("continuation OHLC ranges are invalid")
    close = prices.close
    features = pd.DataFrame({f"return_{lag}": close.pct_change(lag) * 10_000
                             for lag in (1, 3, 6, 12)}, index=bars.index)
    true_range = pd.concat([prices.high - prices.low,
                           (prices.high - close.shift()).abs(),
                           (prices.low - close.shift()).abs()], axis=1).max(axis=1)
    features["atr_20"] = true_range.rolling(20).mean() / close * 10_000
    features["volatility_12"] = close.pct_change().rolling(12).std(ddof=0) * 10_000
    for window in (21, 55):
        features[f"distance_sma_{window}"] = (close / close.rolling(window).mean() - 1) * 10_000
    contiguous = bars.index.to_series().diff().eq(BAR_INTERVAL).rolling(FEATURE_WINDOW_BARS - 1).sum()
    return features.where(contiguous.eq(FEATURE_WINDOW_BARS - 1), np.nan)


def continuation_dataset(bars: pd.DataFrame) -> pd.DataFrame:
    """Label next-open liquidation versus holding exactly another 30 minutes."""
    data = continuation_features(bars)
    endpoint = LABEL_HORIZON_BARS + 1
    data["label_bps"] = (bars.open.shift(-endpoint) / bars.open.shift(-1) - 1) * 10_000
    data["decision_time"] = bars.index + BAR_INTERVAL
    data["label_end"] = bars.index.to_series().shift(-endpoint)
    contiguous = bars.index.to_series().diff().eq(BAR_INTERVAL)
    for offset in range(1, endpoint + 1):
        data = data.loc[contiguous.shift(-offset, fill_value=False).reindex(data.index)]
    return data.dropna()


def purged_folds(samples: pd.DataFrame) -> tuple[tuple[pd.DatetimeIndex, pd.DatetimeIndex], ...]:
    """Return three expanding 40/60/80-percent splits with label-overlap purging."""
    count = len(samples)
    if count < 300:
        raise ValueError("continuation research requires at least 300 usable samples")
    folds: list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]] = []
    for start, end in ((.4, .6), (.6, .8), (.8, 1.0)):
        test = samples.iloc[int(count * start):int(count * end)]
        boundary = test.decision_time.min()
        train = samples.iloc[:int(count * start)]
        train = train.loc[train.label_end < boundary]
        folds.append((train.index, test.index))
    return tuple(folds)
