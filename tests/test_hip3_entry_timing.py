"""Causal entry-timing challengers for the deployed HIP-3 Swing identity."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_entry_timing import (
    Hip3EntryTimingMode,
    build_hip3_entry_timing_signals,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [101.0, 101.0, 100.5, 100.0, 99.0, 99.5, 100.0, 100.0],
            "high": [101.5, 101.4, 101.0, 100.5, 99.5, 100.2, 100.5, 100.5],
            "low": [100.5, 100.2, 99.8, 99.5, 98.5, 99.0, 99.5, 99.5],
            "close": [101.2, 101.1, 100.8, 100.0, 98.8, 99.2, 100.0, 100.0],
            "gap_before_bars": [0] * 8,
        },
        index=index,
    )


def _provider_signals() -> pd.DataFrame:
    index = _bars().index
    return pd.DataFrame(
        {
            "long_alignment": [True, True, True, False, False, False, False, False],
            "short_alignment": [False, False, False, False, True, True, False, False],
            "long_entry": [True, True, True, False, False, False, False, False],
            "short_entry": [False, False, False, False, True, True, False, False],
            "long_exit": [False] * 8,
            "short_exit": [False] * 8,
            "ema_fast": [100.0] * 8,
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("mode", "long_positions", "short_positions"),
    [
        (Hip3EntryTimingMode.PROVIDER_EXACT, [0, 1, 2], [4, 5]),
        (Hip3EntryTimingMode.ALIGNMENT_ONSET, [0], [4]),
        (Hip3EntryTimingMode.NEXT_BAR_CONFIRMATION, [1], [5]),
        (Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK, [2], [5]),
    ],
)
def test_entry_timing_modes_change_only_causal_entry_rows(
    mode: Hip3EntryTimingMode,
    long_positions: list[int],
    short_positions: list[int],
) -> None:
    signals = build_hip3_entry_timing_signals(
        _bars(),
        _provider_signals(),
        mode,
        provider_entry_mode="state",
    )

    assert signals.index[signals["long_entry"]].tolist() == [
        signals.index[position] for position in long_positions
    ]
    assert signals.index[signals["short_entry"]].tolist() == [
        signals.index[position] for position in short_positions
    ]
    assert signals["long_exit"].equals(_provider_signals()["long_exit"])
    assert signals["short_exit"].equals(_provider_signals()["short_exit"])
    assert set(signals["entry_timing_mode"]) == {mode.value}
    assert set(signals["execution_authority"]) == {"none"}


def test_confirmation_and_pullback_do_not_cross_alignment_or_archive_gaps() -> None:
    bars = _bars()
    signals = _provider_signals()
    bars.loc[bars.index[1], "gap_before_bars"] = 2
    signals.loc[bars.index[1], "long_alignment"] = False

    confirmed = build_hip3_entry_timing_signals(
        bars,
        signals,
        Hip3EntryTimingMode.NEXT_BAR_CONFIRMATION,
        provider_entry_mode="state",
    )
    pullback = build_hip3_entry_timing_signals(
        bars,
        signals,
        Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK,
        provider_entry_mode="state",
    )

    assert not confirmed["long_entry"].any()
    assert not pullback["long_entry"].any()
    assert confirmed["short_entry"].sum() == 1
    assert pullback["short_entry"].sum() == 1


def test_entry_timing_rejects_missing_or_misaligned_inputs() -> None:
    bars = _bars()
    signals = _provider_signals().drop(columns="ema_fast")

    with pytest.raises(ValueError, match="missing columns"):
        build_hip3_entry_timing_signals(
            bars,
            signals,
            Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK,
            provider_entry_mode="state",
        )

    shifted = _provider_signals().copy()
    shifted.index = shifted.index + pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match="same index"):
        build_hip3_entry_timing_signals(
            bars,
            shifted,
            Hip3EntryTimingMode.PROVIDER_EXACT,
            provider_entry_mode="state",
        )


def test_onset_provider_uses_only_actual_eligible_provider_events_as_anchors() -> None:
    signals = _provider_signals()
    signals["long_entry"] = [True, False, False, False, False, False, False, False]
    signals["short_entry"] = [False, False, False, False, True, False, False, False]

    onset = build_hip3_entry_timing_signals(
        _bars(),
        signals,
        Hip3EntryTimingMode.ALIGNMENT_ONSET,
        provider_entry_mode="onset",
    )

    assert onset.index[onset["long_entry"]].tolist() == [onset.index[0]]
    assert onset.index[onset["short_entry"]].tolist() == [onset.index[4]]


def test_pre_warmup_nan_ema_is_allowed_only_without_native_alignment() -> None:
    signals = _provider_signals()
    signals.loc[signals.index[0], ["long_alignment", "long_entry"]] = False
    signals.loc[signals.index[0], "ema_fast"] = float("nan")

    result = build_hip3_entry_timing_signals(
        _bars(),
        signals,
        Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK,
        provider_entry_mode="state",
    )
    assert result["execution_authority"].eq("none").all()

    signals.loc[signals.index[0], "long_alignment"] = True
    with pytest.raises(
        ValueError, match="EMA must be finite and positive when aligned"
    ):
        build_hip3_entry_timing_signals(
            _bars(),
            signals,
            Hip3EntryTimingMode.FIRST_FAST_EMA_PULLBACK,
            provider_entry_mode="state",
        )
