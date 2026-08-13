"""Gap-aware literal Swing/Heikin-Ashi signal contracts."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_swing_signals import (
    build_gap_aware_swing_ha_signals,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _bars() -> pd.DataFrame:
    first = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    second = pd.date_range("2026-01-01T04:00:00Z", periods=8, freq="15min")
    index = first.append(second)
    close = [100.0, 102.0, 104.0, 101.0, 99.0, 103.0, 106.0, 108.0]
    close += [108.0, 106.0, 103.0, 105.0, 107.0, 102.0, 99.0, 97.0]
    frame = pd.DataFrame(
        {
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "gap_before_bars": [0] * 8 + [8] + [0] * 7,
            "funding_rate": [0.0] * 16,
        },
        index=index,
    )
    return frame


def test_uses_literal_heikin_ashi_chart_domain_and_symmetric_alignment() -> None:
    config = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    signals = build_gap_aware_swing_ha_signals(_bars(), config)

    assert signals["signal_price_domain"].eq("heikin_ashi_chart").all()
    assert signals["long_alignment"].equals(
        signals["buy_state"] & signals["ha_color"].eq(1)
    )
    assert signals["short_alignment"].equals(
        signals["sell_state"] & signals["ha_color"].eq(-1)
    )
    assert signals["execution_authority"].eq("none").all()


def test_restarts_warmup_and_emits_causal_gap_recovery_exit() -> None:
    config = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    signals = build_gap_aware_swing_ha_signals(_bars(), config)

    assert signals["source_segment_id"].tolist() == [0] * 8 + [1] * 8
    assert signals["signal_warmup"].iloc[:3].all()
    assert signals["signal_warmup"].iloc[8:11].all()
    assert not signals.loc[signals["signal_warmup"], "long_entry"].any()
    assert not signals.loc[signals["signal_warmup"], "short_entry"].any()
    assert signals["gap_recovery_exit"].iloc[8]
    assert signals["long_exit"].iloc[8]
    assert signals["short_exit"].iloc[8]


def test_future_gap_does_not_retroactively_change_prior_signal() -> None:
    config = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    prefix = build_gap_aware_swing_ha_signals(_bars().iloc[:8], config)
    signals = build_gap_aware_swing_ha_signals(_bars(), config)

    assert signals.loc[signals.index[7], ["long_entry", "short_entry"]].equals(
        prefix.loc[prefix.index[7], ["long_entry", "short_entry"]]
    )
    assert not signals["entry_expired_across_gap"].any()


def test_signal_identity_uses_explicit_timeframe() -> None:
    config = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    signals = build_gap_aware_swing_ha_signals(_bars(), config, timeframe="5m")

    assert signals["long_signal_name"].eq("swing_ha_chart_long@5m").all()
    assert signals["short_signal_name"].eq("swing_ha_chart_short@5m").all()
