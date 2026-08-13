"""Tests for the continuous-account Hypervelocity control signal stream."""

from __future__ import annotations

import pandas as pd

from hypervector.research import shared_hypervelocity_signals as module


def test_hypervelocity_signals_preserve_canonical_eligibility(monkeypatch) -> None:
    index = pd.date_range("2026-01-01", periods=7, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {"entry_direction": [None, "long", "long", None, "long", "short", "short"]},
        index=index,
    )
    monkeypatch.setattr(
        module, "classify_multitimeframe", lambda *_args, **_kwargs: decisions
    )

    signals = module.build_hypervelocity_event_signals(_bars(index))

    assert signals["long_entry"].tolist() == [
        False,
        True,
        True,
        False,
        True,
        False,
        False,
    ]
    assert signals["short_entry"].tolist() == [
        False,
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    assert not signals["long_exit"].any()
    assert not signals["short_exit"].any()
    assert set(signals["long_signal_name"]) == {"hypervelocity_control_long"}


def _bars(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Return valid one-minute bars for event construction tests."""
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )
