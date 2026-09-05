from __future__ import annotations

import importlib

import pytest

from btc_trend_pullback_fixtures import pullback_reacceleration_bars


def test_frozen_config_rejects_execution_authority() -> None:
    """Keep the candidate incapable of acquiring live authority."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_reacceleration"
    )
    with pytest.raises(ValueError, match="report-only"):
        module.BtcTrendPullbackConfig(execution_authority="live")


def test_frozen_config_rejects_parameter_drift() -> None:
    """Prevent post-result period or state-window changes."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_reacceleration"
    )
    with pytest.raises(ValueError, match="frozen"):
        module.BtcTrendPullbackConfig(fast_ema_hours=20)


def test_completed_pullback_reacceleration_emits_once() -> None:
    """Emit only after a pullback and a later completed local-high break."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_reacceleration"
    )
    bars, expected_time = pullback_reacceleration_bars()
    result = module.build_btc_trend_pullback_signals(bars)
    entries = result.entries.index[result.entries["long_entry"]]
    assert list(entries) == [expected_time]
    assert result.entries["short_entry"].sum() == 0


def test_gap_marker_resets_pullback_and_hourly_warmup() -> None:
    """Do not carry an armed setup or EMA state across missing evidence."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_reacceleration"
    )
    bars, _ = pullback_reacceleration_bars()
    bars["gap_before_bars"] = 0
    gap_position = 60 * 60 + 30
    bars.iloc[gap_position, bars.columns.get_loc("gap_before_bars")] = 3
    result = module.build_btc_trend_pullback_signals(bars)
    assert result.entries["long_entry"].sum() == 0
    after_gap = result.diagnostics_15m.loc[
        result.diagnostics_15m.index >= bars.index[gap_position].floor("15min")
    ]
    assert not after_gap["trend_up"].fillna(False).any()
