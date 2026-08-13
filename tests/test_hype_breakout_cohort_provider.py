"""Causal tests for the observe-only HYPE breakout-onset provider."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
    HypeBreakoutOnsetCollector,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
    build_hype_entry_features,
)

_BASE_MS = int(pd.Timestamp("2026-08-02T12:00:00Z").timestamp() * 1_000)
_MINUTE_MS = 60_000


def _decision(
    minute: int,
    state_5m: str,
    structural_direction: str,
    breakout_side: str | None = None,
) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=_BASE_MS + minute * _MINUTE_MS,
        reference_price=50.0 + minute,
        long_entry=False,
        short_entry=False,
        long_exit=False,
        short_exit=False,
        primary_regime=state_5m,
        state_1m="TREND_UP" if structural_direction == "long" else "TREND_DOWN",
        state_5m=state_5m,
        context_15m="RANGE",
        confidence=0.60 + minute / 100.0,
        structural_direction=structural_direction,
        regime_admitted=state_5m == "BREAKOUT",
        breakout_side=breakout_side,
    )


def _builder(
    decisions: tuple[SolLiveDecision, ...],
) -> Callable[..., tuple[SolLiveDecision, ...]]:
    def build(
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]:
        del raw_bars
        observed_ms = int(observed_at.timestamp() * 1_000)
        boundary = after_decision_time_ms or 0
        return tuple(
            decision
            for decision in decisions
            if boundary < decision.decision_time_ms <= observed_ms
        )

    return build


def _collector(
    decisions: tuple[SolLiveDecision, ...],
) -> HypeBreakoutOnsetCollector:
    return HypeBreakoutOnsetCollector(decision_builder=_builder(decisions))


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-08-02T12:00:00Z")],
            "open": [50.0],
            "high": [51.0],
            "low": [49.0],
            "close": [50.5],
            "volume": [10.0],
        }
    )


def _attribution_market() -> pd.DataFrame:
    index = pd.date_range("2026-08-02T12:00:00Z", periods=65, freq="1min")
    close = pd.Series([50.0 + position * 0.1 for position in range(65)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": [10.0 + position for position in range(65)],
            "entry_side": [None] * 64 + ["long"],
            "state_1m": ["TREND_UP"] * 65,
            "context_15m": ["TREND_UP"] * 65,
            "sma_gap_bps": [2.0] * 65,
            "regime_strength_score": [0.6] * 65,
            "bbwp_percentile": [50.0] * 49 + [5.0] + [50.0] * 14 + [99.0],
            "ema_gap_bps_signed": [3.0] * 65,
            "rsi": [60.0] * 65,
            "breakout_volume_ratio": [1.5] * 65,
            "regime_5m_strength_percentile": [72.0] * 65,
            "regime_5m_bbwp_percentile": [34.0] * 65,
            "regime_5m_ema_gap_bps": [8.0] * 65,
            "regime_5m_breakout_volume_ratio": [5.2] * 65,
        },
        index=index,
    )


def _attribution_decisions(market: pd.DataFrame) -> tuple[SolLiveDecision, ...]:
    decisions: list[SolLiveDecision] = []
    for position, (timestamp, row) in enumerate(market.iterrows()):
        state_5m = "BREAKOUT" if position == len(market) - 1 else "RANGE"
        decisions.append(
            SolLiveDecision(
                decision_time_ms=int(
                    (pd.Timestamp(timestamp) + pd.Timedelta(minutes=1)).timestamp()
                    * 1_000
                ),
                reference_price=float(row["close"]),
                long_entry=False,
                short_entry=False,
                long_exit=False,
                short_exit=False,
                primary_regime=state_5m,
                state_1m=str(row["state_1m"]),
                state_5m=state_5m,
                context_15m=str(row["context_15m"]),
                confidence=float(row["regime_strength_score"]),
                structural_direction="long",
                regime_admitted=state_5m == "BREAKOUT",
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                volume=float(row["volume"]),
                readiness=SignalReadiness(
                    side="long",
                    conditions_met=1,
                    conditions_required=1,
                    blockers=(),
                    indicators=("TEST SOURCES",),
                    metrics={
                        "sma_gap_bps": float(row["sma_gap_bps"]),
                        "regime_1m_bbwp_percentile": float(row["bbwp_percentile"]),
                        "regime_1m_ema_gap_bps": float(row["ema_gap_bps_signed"]),
                        "rsi": float(row["rsi"]),
                        "regime_1m_breakout_volume_ratio": float(
                            row["breakout_volume_ratio"]
                        ),
                        "regime_5m_strength_percentile": float(
                            row["regime_5m_strength_percentile"]
                        ),
                        "regime_5m_bbwp_percentile": float(
                            row["regime_5m_bbwp_percentile"]
                        ),
                        "regime_5m_ema_gap_bps": float(row["regime_5m_ema_gap_bps"]),
                        "regime_5m_breakout_volume_ratio": float(
                            row["regime_5m_breakout_volume_ratio"]
                        ),
                    },
                ),
            )
        )
    return tuple(decisions)


def test_breakout_transitions_emit_once_in_each_structural_direction() -> None:
    """Persistent breakout bars do not become repeated entry annotations."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long"),
            _decision(3, "BREAKOUT", "long"),
            _decision(4, "RANGE", "short"),
            _decision(5, "BREAKOUT", "short"),
        )
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-02T12:05:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert [(intent.side, intent.decision_time_ms) for intent in batch.intents] == [
        ("long", _BASE_MS + 2 * _MINUTE_MS),
        ("short", _BASE_MS + 5 * _MINUTE_MS),
    ]
    assert batch.latest_decision_time_ms == _BASE_MS + 5 * _MINUTE_MS
    assert [evaluation.eligible for evaluation in batch.evaluations] == [
        True,
        False,
        False,
        True,
    ]
    assert all(
        evaluation.strategy_id == HYPE_BREAKOUT_COHORT_STRATEGY
        for evaluation in batch.evaluations
    )
    first_metrics = batch.evaluations[0].readiness.metrics
    assert first_metrics["entry_feature_status"] == "insufficient_60m_history"
    assert first_metrics["ema_fast_period"] == 21
    assert first_metrics["ema_slow_period"] == 55
    assert first_metrics["ema_semantic_source_identity"] == (
        "hypervector_regime_classifier_completed_close_ema_gap_bps_v1"
    )
    assert first_metrics["ema_gap_directional_bps"] is None


def test_breakout_side_alignment_is_visible_without_changing_the_intent() -> None:
    """Actual 5m direction is report-only beside the hourly structural side."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long", "short"),
        )
    )

    batch = collector(
        _bars(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-02T12:02:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert [intent.side for intent in batch.intents] == ["long"]
    readiness = batch.evaluations[0].readiness
    assert readiness.metrics["breakout_side"] == "short"
    assert readiness.metrics["breakout_side_relation"] == "opposed"
    assert "5M BREAKOUT SHORT / SMA LONG [REPORT ONLY]" in readiness.indicators


def test_breakout_entry_emits_historical_parity_features_report_only() -> None:
    """Live HYPE onset telemetry matches the frozen historical feature contract."""
    market = _attribution_market()
    decisions = _attribution_decisions(market)
    expected = build_hype_entry_features(market).iloc[0]
    collector = _collector(decisions)

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=pd.Timestamp(decisions[-1].decision_time_ms, unit="ms", tz="UTC"),
        after_decision_time_ms=decisions[-2].decision_time_ms,
    )

    assert len(batch.intents) == 1
    metrics = batch.evaluations[0].readiness.metrics
    assert metrics["entry_feature_authority"] == "report_only"
    assert metrics["entry_feature_status"] == "measured"
    assert metrics["ema_fast_period"] == 21
    assert metrics["ema_slow_period"] == 55
    assert metrics["ema_semantic_source_identity"] == (
        "hypervector_regime_classifier_completed_close_ema_gap_bps_v1"
    )
    for name in HYPE_ENTRY_ATTRIBUTION_FEATURES:
        assert metrics[name] == pytest.approx(float(expected[name]))
    payload = batch.evaluations[0].as_payload()
    readiness = payload["readiness"]
    assert isinstance(readiness, dict)
    routed_metrics = readiness["metrics"]
    assert isinstance(routed_metrics, dict)
    assert routed_metrics["ema_fast_period"] == 21
    assert routed_metrics["ema_slow_period"] == 55
    assert routed_metrics["ema_semantic_source_identity"] == (
        "hypervector_regime_classifier_completed_close_ema_gap_bps_v1"
    )


def test_neutral_breakout_onset_is_visible_but_ineligible() -> None:
    """A breakout without a structural side reports the exact blocker."""
    collector = _collector(
        (
            _decision(1, "RANGE", "neutral"),
            _decision(2, "BREAKOUT", "neutral"),
        )
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-02T12:02:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert batch.intents == ()
    evaluation = batch.evaluations[0]
    assert evaluation.eligible is False
    assert evaluation.reason == "structural_direction_neutral"
    assert evaluation.readiness.conditions_met == 2
    assert evaluation.readiness.conditions_required == 3
    assert evaluation.readiness.blockers == ("structural_direction_neutral",)
    assert evaluation.readiness.metrics["breakout_onset"] is True
    assert evaluation.readiness.metrics["entry_feature_status"] == (
        "neutral_side_unavailable"
    )
    assert all(
        evaluation.readiness.metrics[name] is None
        for name in HYPE_ENTRY_ATTRIBUTION_FEATURES
    )


def test_startup_seed_never_emits_a_retroactive_breakout_intent() -> None:
    """Earlier readiness queries remain annotation-only after activation."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long"),
            _decision(3, "BREAKOUT", "long"),
        )
    )
    activation = _BASE_MS + 3 * _MINUTE_MS
    first = collector(
        _bars(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-02T12:03:00Z"),
        after_decision_time_ms=activation,
    )
    seed = collector(
        _bars(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-02T12:03:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert first.intents == ()
    assert first.evaluations == ()
    assert seed.intents == ()
    assert len(seed.evaluations) == 2
    assert seed.evaluations[0].eligible is True


def test_provider_rejects_unsupported_symbols() -> None:
    """The measured observer cannot silently expand beyond enabled assets."""
    collector = _collector((_decision(1, "RANGE", "long"),))

    with pytest.raises(ValueError, match="supports BTC/ETH/SOL/HYPE only"):
        collector(
            _bars(),
            symbol="DOGE",
            observed_at=pd.Timestamp("2026-08-02T12:01:00Z"),
            after_decision_time_ms=_BASE_MS,
        )


def test_observer_preserves_the_requested_non_hype_symbol() -> None:
    """Observer expansion must retain exact provider-symbol attribution."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long"),
        )
    )

    batch = collector(
        _bars(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-02T12:02:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert [intent.symbol for intent in batch.intents] == ["BTC"]
    assert [evaluation.symbol for evaluation in batch.evaluations] == ["BTC"]


def test_startup_seed_detection_is_isolated_per_symbol() -> None:
    """A faster symbol boundary cannot suppress another symbol's live onset."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long"),
            _decision(3, "BREAKOUT", "long"),
            _decision(4, "RANGE", "long"),
            _decision(5, "RANGE", "long"),
        )
    )
    collector(
        _bars(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-02T12:05:00Z"),
        after_decision_time_ms=_BASE_MS + 5 * _MINUTE_MS,
    )

    batch = collector(
        _bars(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-02T12:02:00Z"),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert [(intent.symbol, intent.side) for intent in batch.intents] == [
        ("ETH", "long")
    ]
