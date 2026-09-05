"""Causal signal tests for the HIP-3 cash-open gap reversal."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
    cash_session_bar_opens,
)


_DECISION = pd.Timestamp("2026-06-10T13:30:00Z")
_SESSION_EXIT = pd.Timestamp("2026-06-10T19:45:00Z")


def _bars(*, gap_bps: float, first_close: float | None = None) -> pd.DataFrame:
    index = pd.date_range(
        "2026-06-09T19:30:00Z",
        "2026-06-10T20:00:00Z",
        freq="15min",
        inclusive="left",
    )
    frame = pd.DataFrame(100.0, index=index, columns=["open", "high", "low", "close"])
    frame["gap_before_bars"] = 0
    prior_close_row = pd.Timestamp("2026-06-09T19:45:00Z")
    frame.loc[prior_close_row, ["open", "high", "low", "close"]] = [
        99.9,
        100.1,
        99.8,
        100.0,
    ]
    opening = 100.0 * (1.0 + gap_bps / 10_000.0)
    close = first_close if first_close is not None else opening
    frame.loc[_DECISION, ["open", "high", "low", "close"]] = [
        opening,
        max(opening, close) + 0.05,
        min(opening, close) - 0.05,
        close,
    ]
    return frame


@pytest.mark.parametrize(
    ("gap_bps", "entry_column", "signal_name", "stop_side"),
    [
        (30.0, "short_entry", "hip3_cash_open_gap_reversal_short@15m", "above"),
        (-30.0, "long_entry", "hip3_cash_open_gap_reversal_long@15m", "below"),
    ],
)
def test_large_gap_fades_after_first_completed_bar(
    gap_bps: float,
    entry_column: str,
    signal_name: str,
    stop_side: str,
) -> None:
    """Enter opposite a still-open 20-bps gap with prior-close target."""
    signals = build_hip3_cash_open_gap_reversal_signals(
        _bars(gap_bps=gap_bps), Hip3CashOpenGapReversalConfig()
    )
    row = signals.loc[_DECISION]
    assert row[entry_column]
    assert row["signal_name"] == signal_name
    assert row["target_price"] == pytest.approx(100.0)
    if stop_side == "above":
        assert row["stop_price"] > 100.0
    else:
        assert row["stop_price"] < 100.0
    assert row["execution_authority"] == "none"


def test_subthreshold_gap_is_not_an_entry() -> None:
    """Keep the primary-paper 20-bps filter fixed."""
    signals = build_hip3_cash_open_gap_reversal_signals(
        _bars(gap_bps=19.9), Hip3CashOpenGapReversalConfig()
    )
    assert not signals.loc[_DECISION, ["long_entry", "short_entry"]].any()


@pytest.mark.parametrize(
    ("gap_bps", "first_close"),
    [(30.0, 99.95), (-30.0, 100.05)],
)
def test_gap_already_reverted_before_decision_is_not_chased(
    gap_bps: float, first_close: float
) -> None:
    """Reject a reversal whose prior-close target was already crossed."""
    signals = build_hip3_cash_open_gap_reversal_signals(
        _bars(gap_bps=gap_bps, first_close=first_close),
        Hip3CashOpenGapReversalConfig(),
    )
    assert not signals.loc[_DECISION, ["long_entry", "short_entry"]].any()


def test_session_close_is_a_symmetric_fallback_exit() -> None:
    """Close either side after the final completed cash-session bar."""
    signals = build_hip3_cash_open_gap_reversal_signals(
        _bars(gap_bps=30.0), Hip3CashOpenGapReversalConfig()
    )
    assert signals.loc[_SESSION_EXIT, "long_exit"]
    assert signals.loc[_SESSION_EXIT, "short_exit"]


def test_declared_early_close_becomes_exit_and_next_prior_close() -> None:
    """A shortened cash session must not wait for a nonexistent 16:00 close."""
    index = pd.date_range(
        "2026-11-25T20:45:00Z",
        "2026-11-30T14:00:00Z",
        freq="15min",
        inclusive="left",
    )
    frame = pd.DataFrame(100.0, index=index, columns=["open", "high", "low", "close"])
    frame["gap_before_bars"] = 0
    early_close = pd.Timestamp("2026-11-27T17:45:00Z")
    monday_open = pd.Timestamp("2026-11-30T14:30:00Z")
    frame.loc[early_close, ["open", "high", "low", "close"]] = 101.0
    frame = pd.concat(
        [
            frame,
            pd.DataFrame(
                {
                    "open": [101.3],
                    "high": [101.3],
                    "low": [101.3],
                    "close": [101.3],
                    "gap_before_bars": [0],
                },
                index=pd.DatetimeIndex([monday_open]),
            ),
        ]
    ).sort_index()
    config = Hip3CashOpenGapReversalConfig(
        closed_session_dates=(date(2026, 11, 26),),
        early_close_minutes=((date(2026, 11, 27), 765),),
    )

    signals = build_hip3_cash_open_gap_reversal_signals(frame, config)

    assert signals.loc[early_close, "long_exit"]
    assert signals.loc[early_close, "short_exit"]
    assert signals.loc[monday_open, "previous_cash_close"] == pytest.approx(101.0)


def test_recovery_decision_and_declared_closure_are_censored() -> None:
    """Do not signal on a source recovery row or a closed cash session."""
    recovery = _bars(gap_bps=30.0)
    recovery.loc[_DECISION, "gap_before_bars"] = 1
    recovered = build_hip3_cash_open_gap_reversal_signals(
        recovery, Hip3CashOpenGapReversalConfig()
    )
    closed = build_hip3_cash_open_gap_reversal_signals(
        _bars(gap_bps=30.0),
        Hip3CashOpenGapReversalConfig(closed_session_dates=(date(2026, 6, 10),)),
    )
    assert not recovered.loc[_DECISION, ["long_entry", "short_entry"]].any()
    assert not closed.loc[_DECISION, ["long_entry", "short_entry"]].any()


def test_gap_affected_prior_close_cannot_be_an_entry_target() -> None:
    """An unresolved prior close must not supply a tradable target anchor."""
    bars = _bars(gap_bps=30.0)
    prior_close = pd.Timestamp("2026-06-09T19:45:00Z")
    bars.loc[prior_close, "gap_before_bars"] = 1

    signals = build_hip3_cash_open_gap_reversal_signals(
        bars,
        Hip3CashOpenGapReversalConfig(),
    )

    assert pd.isna(signals.loc[_DECISION, "previous_cash_close"])
    assert not signals.loc[_DECISION, ["long_entry", "short_entry"]].any()


def test_later_prices_cannot_rewrite_the_cash_open_decision() -> None:
    """Prove signal construction does not consume post-decision bars."""
    baseline = _bars(gap_bps=30.0)
    changed = baseline.copy()
    changed.loc[changed.index > _DECISION, ["open", "high", "low", "close"]] *= 1.5
    left = build_hip3_cash_open_gap_reversal_signals(
        baseline, Hip3CashOpenGapReversalConfig()
    ).loc[_DECISION]
    right = build_hip3_cash_open_gap_reversal_signals(
        changed, Hip3CashOpenGapReversalConfig()
    ).loc[_DECISION]
    columns = ["long_entry", "short_entry", "stop_price", "target_price"]
    pd.testing.assert_series_equal(left[columns], right[columns])


def test_complete_cash_window_matches_prior_dense_signal_path() -> None:
    """Session filtering must preserve every complete-window strategy output."""
    dense = _bars(gap_bps=30.0)
    config = Hip3CashOpenGapReversalConfig()
    scheduled = cash_session_bar_opens(
        int(dense.index[0].timestamp() * 1_000),
        int((dense.index[-1] + pd.Timedelta(minutes=15)).timestamp() * 1_000),
        config,
    )
    cash_index = dense.index.intersection(scheduled)

    dense_signals = build_hip3_cash_open_gap_reversal_signals(dense, config).loc[
        cash_index
    ]
    sparse_signals = build_hip3_cash_open_gap_reversal_signals(
        dense.loc[cash_index],
        config,
    )

    pd.testing.assert_frame_equal(dense_signals, sparse_signals)
