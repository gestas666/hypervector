"""Tests for conservative low-timeframe directional barrier labels."""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from hypervector.research.low_tf_barriers import (
    DirectionalBarrierSpec,
    label_directional_barriers,
)


def _bars(rows: int = 14) -> pd.DataFrame:
    opens = pd.date_range("2026-01-01", periods=rows, freq="5min", tz=UTC)
    return pd.DataFrame(
        {
            "bar_open_at": opens,
            "open": [100.0] * rows,
            "high": [100.1] * rows,
            "low": [99.9] * rows,
            "close": [100.0] * rows,
        }
    )


def _outcomes(bars: pd.DataFrame) -> pd.DataFrame:
    signal = pd.DatetimeIndex([bars.loc[0, "bar_open_at"]])
    return label_directional_barriers(bars, signal, DirectionalBarrierSpec())


def test_long_target_and_short_stop_are_side_aware() -> None:
    """The same future path must be normalized independently for each side."""
    bars = _bars()
    bars.loc[1, ["high", "low", "close"]] = [100.30, 99.90, 100.20]

    outcomes = _outcomes(bars).set_index("side")

    assert outcomes.loc["long", "status"] == "target"
    assert outcomes.loc["long", "gross_return_bps"] == pytest.approx(25.0)
    assert outcomes.loc["short", "status"] == "stop"
    assert outcomes.loc["short", "gross_return_bps"] == pytest.approx(-18.0)


def test_short_target_and_long_stop_are_side_aware() -> None:
    """Downward paths must produce the mirror directional outcomes."""
    bars = _bars()
    bars.loc[1, ["high", "low", "close"]] = [100.10, 99.70, 99.80]

    outcomes = _outcomes(bars).set_index("side")

    assert outcomes.loc["short", "status"] == "target"
    assert outcomes.loc["short", "gross_return_bps"] == pytest.approx(25.0)
    assert outcomes.loc["long", "status"] == "stop"
    assert outcomes.loc["long", "gross_return_bps"] == pytest.approx(-18.0)


def test_same_bar_target_and_stop_resolves_adverse_first() -> None:
    """OHLC ambiguity must not receive optimistic target-first treatment."""
    bars = _bars()
    bars.loc[1, ["high", "low"]] = [100.30, 99.70]

    outcomes = _outcomes(bars)

    assert outcomes["status"].eq("ambiguous_stop_first").all()
    assert outcomes["ambiguous"].all()
    assert outcomes["gross_return_bps"].eq(-18.0).all()


def test_timeout_uses_final_horizon_close() -> None:
    """A no-touch path exits at the twelfth completed future-bar close."""
    bars = _bars()
    bars.loc[12, "close"] = 100.05

    outcomes = _outcomes(bars).set_index("side")

    assert outcomes["status"].eq("timeout").all()
    assert outcomes.loc["long", "gross_return_bps"] == pytest.approx(5.0)
    assert outcomes.loc["short", "gross_return_bps"] == pytest.approx(-5.0)
    assert outcomes.loc["long", "outcome_time_utc"] == (
        bars.loc[12, "bar_open_at"] + pd.Timedelta(minutes=5)
    )


def test_truncated_horizon_is_not_fabricated_as_timeout() -> None:
    """Evidence ending before twelve future bars must remain censored."""
    bars = _bars(rows=5)

    outcomes = _outcomes(bars)

    assert outcomes["status"].eq("truncated").all()
    assert outcomes["gross_return_bps"].isna().all()


def test_missing_immediate_entry_bar_is_truncated() -> None:
    """A five-minute gap after the signal cannot be crossed silently."""
    bars = _bars()
    bars = bars.drop(index=1).reset_index(drop=True)

    outcomes = _outcomes(bars)

    assert outcomes["status"].eq("truncated").all()
    assert outcomes["entry_time_utc"].isna().all()


def test_unknown_signal_timestamp_is_rejected() -> None:
    """Signal identity must correspond to an observed completed bar."""
    bars = _bars()
    unknown = pd.DatetimeIndex([pd.Timestamp("2025-12-01", tz=UTC)])

    with pytest.raises(ValueError, match="signal timestamp"):
        label_directional_barriers(bars, unknown, DirectionalBarrierSpec())
