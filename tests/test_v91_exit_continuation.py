"""Leakage and replay requirements for prospective exit continuation research."""

import numpy as np
import pandas as pd

from hypervector.research.v91_exit_continuation import continuation_dataset, continuation_features, purged_folds


def frame() -> pd.DataFrame:
    """Return enough deterministic contiguous candles for three time splits."""
    index = pd.date_range("2026-07-01", periods=800, freq="15min", tz="UTC")
    close = 100 + np.arange(800) / 100 + np.sin(np.arange(800) / 5)
    return pd.DataFrame({"open": close, "high": close + .2, "low": close - .2, "close": close}, index=index)


def test_features_do_not_change_when_future_prices_change() -> None:
    """Future rows cannot alter the decision-time feature vector."""
    data = frame()
    original = continuation_features(data)
    data.iloc[400:] *= 3
    pd.testing.assert_frame_equal(original.iloc[:400], continuation_features(data).iloc[:400])


def test_label_uses_next_open_and_thirty_minute_hold() -> None:
    """Training reward matches execution after the completed source bar."""
    data = frame()
    samples = continuation_dataset(data)
    stamp = data.index[100]
    expected = (data.iloc[103].open / data.iloc[101].open - 1) * 10_000
    assert np.isclose(samples.loc[stamp, "label_bps"], expected)
    assert samples.loc[stamp, "label_end"] == data.index[103]


def test_folds_purge_every_label_reaching_the_test_period() -> None:
    """No training outcome crosses a held-out decision boundary."""
    samples = continuation_dataset(frame())
    folds = purged_folds(samples)
    assert len(folds) == 3
    for train, test in folds:
        assert samples.loc[train, "label_end"].max() < samples.loc[test, "decision_time"].min()
        assert set(train).isdisjoint(test)


def test_missing_candle_breaks_feature_and_label_windows() -> None:
    """Missing timestamps cannot silently shorten a forecast horizon."""
    data = frame().drop(frame().index[100])
    samples = continuation_dataset(data)
    assert frame().index[99] not in samples.index
    assert frame().index[101] not in samples.index
