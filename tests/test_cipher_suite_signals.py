"""Tests for causal Cipher A, Cipher B, and DBSI state composition."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd

from hypervector.research.cipher_suite_signals import (
    CIPHER_VARIANTS,
    cipher_b_cross_events_from_waves,
    cipher_b_events_from_waves,
    cipher_b_states_from_waves,
    compose_cipher_bundle_entries,
    compose_cipher_entries,
    pine_aroon_bullish,
    pine_mfi_source,
    state_from_events,
)


def test_state_from_events_persists_and_neutralizes_simultaneous_events() -> None:
    """A component vote must persist until one unambiguous opposite event."""
    long_events = np.array([False, True, False, True, False, False])
    short_events = np.array([False, False, False, True, False, True])

    states = state_from_events(long_events, short_events)

    assert states.tolist() == [0, 1, 1, 1, 1, -1]


def test_cipher_b_uses_pine_cross_direction_and_wt2_extremes() -> None:
    """Bullish means WT1 crosses above WT2 while WT2 is oversold."""
    wt1 = np.array([-60.0, -58.0, -50.0, 58.0, 50.0])
    wt2 = np.array([-55.0, -55.0, -54.0, 55.0, 54.0])

    states = cipher_b_states_from_waves(wt1, wt2)

    assert states.tolist() == [0, 0, 1, 1, -1]


def test_cipher_b_events_are_pulses_not_persisted_direction() -> None:
    """The combined strategy must time entries only on the B cross bar."""
    wt1 = np.array([-60.0, -58.0, -50.0, 58.0, 50.0])
    wt2 = np.array([-55.0, -55.0, -54.0, 55.0, 54.0])

    events = cipher_b_events_from_waves(wt1, wt2)

    assert events.tolist() == [0, 0, 1, 0, -1]


def test_cipher_b_small_dot_is_any_wavetrend_cross() -> None:
    """The Pine small dot/VWAP zero-cross must not require an extreme level."""
    wt1 = np.array([-10.0, 2.0, 3.0, -2.0])
    wt2 = np.array([-5.0, -1.0, 1.0, 1.0])

    events = cipher_b_cross_events_from_waves(wt1, wt2)

    assert events.tolist() == [0, 1, 0, -1]


def test_pine_mfi_uses_supplied_source_not_hlc3() -> None:
    """Pine ta.mfi(close, n) must classify flow from close changes."""
    source = np.array([10.0, 11.0, 10.0, 12.0, 11.0])
    volume = np.ones(5)

    result = pine_mfi_source(source, volume, period=2)

    assert np.isnan(result[:2]).all()
    assert result[2] == 100.0 * 11.0 / 21.0
    assert result[3] == 100.0 * 12.0 / 22.0
    assert result[4] == 100.0 * 12.0 / 23.0


def test_pine_aroon_uses_fourteen_bars_and_most_recent_ties() -> None:
    """DBSI Aroon must follow highestbars/lowestbars over exactly 14 bars."""
    high = np.arange(1.0, 16.0)
    low = np.arange(20.0, 35.0)

    bullish = pine_aroon_bullish(high, low, period=14)

    assert not bullish[:13].any()
    assert bullish[13]
    assert bullish[14]


def test_compositions_emit_only_causal_state_transitions() -> None:
    """Bundled votes must enter on state onset, not on every active bar."""
    index = pd.date_range("2026-01-01", periods=6, freq="5min", tz=UTC)
    states = pd.DataFrame(
        {
            "cipher_a": [0, 1, 1, 1, -1, -1],
            "cipher_b": [0, 0, 1, 1, -1, -1],
            "cipher_dbsi": [0, 1, 1, -1, -1, -1],
        },
        index=index,
    )

    entries = compose_cipher_entries(states)

    all_two = entries.loc[entries["candidate"].eq("cipher_a_b_all")]
    assert all_two[["signal_time_utc", "side"]].values.tolist() == [
        [index[2], "long"],
        [index[4], "short"],
    ]
    suite_two = entries.loc[entries["candidate"].eq("cipher_suite_2of3")]
    assert suite_two[["signal_time_utc", "side"]].values.tolist() == [
        [index[1], "long"],
        [index[4], "short"],
    ]
    assert set(entries["candidate"]) == set(CIPHER_VARIANTS)


def test_cipher_bundle_uses_a_as_trend_b_as_trigger_and_dbsi_as_confirmation() -> None:
    """B pulses must fire only when A aligns; DBSI is a strict optional confirm."""
    index = pd.date_range("2026-01-01", periods=5, freq="15min", tz=UTC)
    components = pd.DataFrame(
        {
            "cipher_a_trend": [1, 1, -1, -1, -1],
            "cipher_b_trigger": [0, 1, -1, -1, 1],
            "cipher_b_cross_trigger": [1, 1, -1, -1, 1],
            "cipher_b_money_flow": [1, -1, -1, 1, 1],
            "cipher_dbsi": [1, -1, -1, 1, 1],
        },
        index=index,
    )

    entries = compose_cipher_bundle_entries(components)

    base = entries.loc[entries["candidate"].eq("cipher_a_b_trigger")]
    strict = entries.loc[entries["candidate"].eq("cipher_a_b_dbsi_trigger")]
    assert base[["signal_time_utc", "side"]].values.tolist() == [
        [index[1], "long"],
        [index[2], "short"],
        [index[3], "short"],
    ]
    assert strict[["signal_time_utc", "side"]].values.tolist() == [[index[2], "short"]]
    cross = entries.loc[entries["candidate"].eq("cipher_a_b_cross")]
    flow = entries.loc[entries["candidate"].eq("cipher_a_b_flow_cross")]
    assert cross[["signal_time_utc", "side"]].values.tolist() == [
        [index[0], "long"],
        [index[1], "long"],
        [index[2], "short"],
        [index[3], "short"],
    ]
    assert flow[["signal_time_utc", "side"]].values.tolist() == [
        [index[0], "long"],
        [index[2], "short"],
    ]
