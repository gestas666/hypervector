"""Causal order-block contracts for the Swing/HA challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.swing_order_blocks import build_order_block_state


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)


def test_bullish_block_is_available_only_after_followthrough_completes() -> None:
    bars = _bars(
        [
            (10.0, 10.5, 8.5, 9.0),
            (9.0, 10.2, 8.8, 10.0),
            (10.0, 11.2, 9.8, 11.0),
            (11.0, 12.2, 10.8, 12.0),
            (12.0, 12.5, 11.5, 12.1),
        ]
    )

    result = build_order_block_state(bars, periods=3, minimum_move_pct=0.0)

    assert result["bull_ob_detected"].iloc[:4].eq(False).all()
    assert result["bull_ob_detected"].iloc[4]
    assert result["active_bull_ob_low"].iloc[4] == pytest.approx(8.5)
    assert result["active_bull_ob_high"].iloc[4] == pytest.approx(10.0)
    assert result["bull_ob_source_position"].iloc[4] == pytest.approx(0.0)


def test_displacement_threshold_filters_weak_block() -> None:
    bars = _bars(
        [
            (100.0, 100.2, 99.7, 99.9),
            (99.9, 100.1, 99.8, 100.0),
            (100.0, 100.2, 99.9, 100.1),
            (100.1, 100.3, 100.0, 100.2),
            (100.2, 100.4, 100.1, 100.3),
        ]
    )

    result = build_order_block_state(bars, periods=3, minimum_move_pct=0.5)

    assert not result["bull_ob_detected"].any()


def test_active_bull_block_invalidates_on_close_below_low() -> None:
    bars = _bars(
        [
            (10.0, 10.5, 8.5, 9.0),
            (9.0, 10.2, 8.8, 10.0),
            (10.0, 11.2, 9.8, 11.0),
            (11.0, 12.2, 10.8, 12.0),
            (12.0, 12.5, 11.5, 12.1),
            (12.1, 12.2, 8.0, 8.4),
        ]
    )

    result = build_order_block_state(bars, periods=3, minimum_move_pct=0.0)

    assert result["active_bull_ob_low"].iloc[4] == pytest.approx(8.5)
    assert pd.isna(result["active_bull_ob_low"].iloc[5])


def test_future_append_does_not_change_prior_order_block_state() -> None:
    base = _bars(
        [
            (10, 11, 8, 9),
            (9, 10, 8, 10),
            (10, 11, 9, 11),
            (11, 12, 10, 12),
            (12, 13, 11, 12.5),
        ]
    )
    extended = pd.concat(
        [
            base,
            _bars([(12.5, 13, 11, 11.5), (11.5, 12, 10, 10.5)]).set_axis(
                pd.date_range(
                    base.index[-1] + pd.Timedelta(minutes=15),
                    periods=2,
                    freq="15min",
                    tz="UTC",
                )
            ),
        ]
    )

    before = build_order_block_state(base, periods=3, minimum_move_pct=0.0)
    after = build_order_block_state(extended, periods=3, minimum_move_pct=0.0).iloc[
        : len(base)
    ]

    pd.testing.assert_frame_equal(before, after)
