"""Causal candle-to-live-decision conversion tests."""

from __future__ import annotations

import pandas as pd
from pytest import MonkeyPatch

from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-31T06:00:00Z", periods=3, freq="1min"),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 11.0, 12.0],
        }
    )


def _signals(bars: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(
        False,
        index=bars.index,
        columns=["long_entry", "short_entry", "long_exit", "short_exit"],
    )
    result["structural_direction"] = "long"
    result["regime_admitted"] = True
    result["raw_long_cross"] = False
    result["raw_short_cross"] = False
    result["sma_fast"] = 101.0
    result["sma_slow"] = 100.0
    result["sma_gap_bps"] = 100.0
    result.iloc[-1, result.columns.get_loc("long_entry")] = True
    result.iloc[-1, result.columns.get_loc("raw_long_cross")] = True
    return result


def _regimes(bars: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": "RANGE",
            "state_1m": "RANGE",
            "state_5m": "BREAKOUT",
            "structural_direction": "short",
            "context_15m": "TREND_UP",
            "confidence": 0.7,
            "rsi": 57.5,
            "regime_1m_reason": "range_structure",
            "regime_5m_reason": "breakout_structure",
            "regime_15m_reason": "trend_structure",
            "regime_1m_strength_percentile": 20.0,
            "regime_5m_strength_percentile": 70.0,
            "regime_15m_strength_percentile": 80.0,
            "regime_1m_bbwp_percentile": 12.0,
            "regime_5m_bbwp_percentile": 30.0,
            "regime_15m_bbwp_percentile": 50.0,
            "regime_1m_ema_gap_bps": 0.5,
            "regime_5m_ema_gap_bps": 8.0,
            "regime_15m_ema_gap_bps": 12.0,
            "regime_1m_coiling": True,
            "regime_5m_coiling": False,
            "regime_15m_coiling": False,
            "regime_1m_range_cause_coiling": True,
            "regime_5m_range_cause_coiling": False,
            "regime_15m_range_cause_coiling": False,
            "regime_1m_range_cause_strength": True,
            "regime_5m_range_cause_strength": False,
            "regime_15m_range_cause_strength": False,
            "regime_1m_range_cause_gap": True,
            "regime_5m_range_cause_gap": False,
            "regime_15m_range_cause_gap": False,
            "regime_1m_range_cause_filter": True,
            "regime_5m_range_cause_filter": False,
            "regime_15m_range_cause_filter": False,
            "regime_1m_breakout_volume_ratio": 0.8,
            "regime_5m_breakout_volume_ratio": 2.7,
            "regime_15m_breakout_volume_ratio": 1.1,
            "regime_range_filter_name": "bbwp",
            "regime_bbwp_threshold_pct": 25.0,
            "regime_minimum_gap_bps": 5.0,
            "regime_range_strength_threshold_pct": 30.0,
            "regime_trend_strength_threshold_pct": 60.0,
            "regime_breakout_volume_multiple": 2.5,
        },
        index=bars.index,
    )


def test_only_completed_unseen_bars_become_live_decisions(
    monkeypatch: MonkeyPatch,
) -> None:
    """The in-progress candle and already processed timestamp are excluded."""
    import hypervector.live.sol_range_onset_decision_source as module

    monkeypatch.setattr(module, "build_range_onset_signals", _signals)
    monkeypatch.setattr(module, "classify_multitimeframe", _regimes)
    after = int(pd.Timestamp("2026-07-31T06:01:00Z").timestamp() * 1_000)

    decisions = build_completed_live_decisions(
        _bars(),
        observed_at=pd.Timestamp("2026-07-31T06:02:30Z"),
        after_decision_time_ms=after,
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision_time_ms == int(
        pd.Timestamp("2026-07-31T06:02:00Z").timestamp() * 1_000
    )
    assert decision.reference_price == 101.5
    assert decision.long_entry is True
    assert decision.state_5m == "BREAKOUT"
    assert decision.breakout_side == "short"
    assert decision.context_15m == "TREND_UP"
    assert decision.open_price == 101.0
    assert decision.high_price == 102.0
    assert decision.low_price == 100.0
    assert decision.volume == 11.0
    assert decision.as_payload()["open"] == 101.0
    assert decision.as_payload()["breakout_side"] == "short"
    assert decision.readiness is not None
    assert decision.readiness.conditions_met == 3
    assert decision.readiness.conditions_required == 3
    assert "SMA GAP +100.0bps" in decision.readiness.indicators
    expected = {
        "raw_long_cross": True,
        "raw_short_cross": False,
        "regime_admitted": True,
        "sma_fast": 101.0,
        "sma_gap_bps": 100.0,
        "sma_slow": 100.0,
        "structural_direction": "long",
    }
    assert all(
        decision.readiness.metrics[key] == value for key, value in expected.items()
    )
    assert decision.readiness.metrics["component_authority"] == "observe_only"
    assert float(decision.readiness.metrics["ema_21_55_gap_bps"]) > 0.0
    assert type(decision.readiness.metrics["ema_21_55_direction"]) is int
    assert type(decision.readiness.metrics["cipher_a_direction"]) is int
    assert type(decision.readiness.metrics["harsi_direction"]) is int
    assert decision.readiness.metrics["self_aware_tqi"] is None
    assert decision.readiness.metrics["regime_5m_bbwp_percentile"] == 30.0
    assert decision.readiness.metrics["rsi"] == 57.5
    assert decision.readiness.metrics["regime_1m_range_cause_filter"] is True
    assert decision.readiness.metrics["regime_range_filter_name"] == "bbwp"
    assert "5M BBWP 30.0/25.0" in decision.readiness.indicators


def test_naive_observation_time_is_rejected() -> None:
    """Live causality cannot depend on an implicit local timezone."""
    try:
        build_completed_live_decisions(
            _bars(),
            observed_at=pd.Timestamp("2026-07-31T06:02:30"),
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive observed_at must be rejected")


def test_dual_mtf_challenger_is_visible_without_gating_entry(
    monkeypatch: MonkeyPatch,
) -> None:
    """Opposing context is research telemetry and cannot alter source readiness."""
    import hypervector.live.sol_range_onset_decision_source as module

    monkeypatch.setattr(module, "build_range_onset_signals", _signals)
    monkeypatch.setattr(module, "classify_multitimeframe", _regimes)
    monkeypatch.setattr(
        module,
        "build_regime_component_frame",
        lambda bars: pd.DataFrame(
            {"mtf_5m_bias": -3.0, "mtf_15m_bias": -3.0},
            index=bars.index,
        ),
    )

    decision = build_completed_live_decisions(
        _bars(),
        observed_at=pd.Timestamp("2026-07-31T06:02:30Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-07-31T06:01:00Z").timestamp() * 1_000
        ),
    )[0]

    assert decision.long_entry is True
    assert decision.readiness.conditions_met == 3
    assert decision.readiness.blockers == ()
    assert decision.readiness.metrics["dual_mtf_context_challenger_admitted"] is False
    assert (
        decision.readiness.metrics["dual_mtf_context_challenger_authority"]
        == "report_only"
    )
    assert "DUAL-MTF CHALLENGER OPPOSED [REPORT ONLY]" in (
        decision.readiness.indicators
    )
