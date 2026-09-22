"""Causal and semantic boundaries of the frozen V92 entry candidates."""

import numpy as np
import pandas as pd
import pytest

from hypervector.research.v92_entry_candidates import build_v92_signals


def _bars(hours: int = 90) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=hours * 4, freq="15min", tz="UTC")
    close = 100 + np.arange(len(index)) * 0.01
    return pd.DataFrame(
        {"open": close, "high": close + 0.1, "low": close - 0.1, "close": close},
        index=index,
    )


@pytest.mark.parametrize("candidate", ["donchian", "donchian_bounded", "trend"])
def test_future_prices_cannot_change_past_signals(candidate: str) -> None:
    bars = _bars()
    full = build_v92_signals(bars, candidate)
    prefix = build_v92_signals(bars.iloc[:301], candidate)
    pd.testing.assert_frame_equal(full.iloc[:301], prefix)


def test_trend_can_enter_an_existing_trend_without_fresh_cross() -> None:
    result = build_v92_signals(_bars(), "trend")
    assert result.long_entry.iloc[-1]
    assert result.long_entry.sum() > 10
    assert not result.short_entry.any()
    assert all(stamp.minute == 45 for stamp in result.index[result.long_entry])
    assert not result.long_entry.iloc[: 55 * 4 - 1].any()


def test_trend_short_symmetry() -> None:
    bars = _bars()
    inverted = pd.DataFrame(
        {
            "open": 200 - bars.open,
            "high": 200 - bars.low,
            "low": 200 - bars.high,
            "close": 200 - bars.close,
        }
    )
    result = build_v92_signals(inverted, "trend")
    assert result.short_entry.iloc[-1]
    assert not result.long_entry.any()


def test_extended_breakout_refuses_entry_but_retains_exit() -> None:
    bars = _bars()
    bars.loc[bars.index[-4:], ["open", "high", "low", "close"]] += 10
    raw = build_v92_signals(bars, "donchian")
    bounded = build_v92_signals(bars, "donchian_bounded")
    assert raw.long_entry.iloc[-1]
    assert bounded.entry_extension_atr.iloc[-1] > 1
    assert not bounded.long_entry.iloc[-1]
    assert bounded.short_exit.iloc[-1]
    assert bounded.entry_rejected_extension.iloc[-1]


def test_gap_requires_new_indicator_warmup() -> None:
    bars = _bars().drop(_bars().index[240:244])
    result = build_v92_signals(bars, "trend")
    assert not result.long_entry.iloc[240:].any()


def test_unknown_candidate_fails_explicitly() -> None:
    with pytest.raises(ValueError, match="candidate"):
        build_v92_signals(_bars(), "unknown")
