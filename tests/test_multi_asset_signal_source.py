"""Attribution tests for multi-asset bidirectional signal providers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.multi_asset_signal_source import (
    build_hulk_bidirectional_intents,
    build_range_onset_bidirectional_intents,
    collect_hulk_bidirectional_intents,
    collect_range_onset_bidirectional_intents,
    ProviderEvaluation,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_controller import SolLiveDecision


def _hulk(side: str, offset: int) -> HulkSmashLiveDecision:
    timestamp = pd.Timestamp("2026-08-01T12:00:00Z") + pd.Timedelta(minutes=30 * offset)
    return HulkSmashLiveDecision(
        decision_time_ms=int(
            (timestamp + pd.Timedelta(minutes=30)).timestamp() * 1_000
        ),
        bar_open_at=timestamp,
        reference_price=100.0,
        open_price=99.5,
        high_price=100.5,
        low_price=99.0,
        volume=10.0,
        candidate="hulk_rebuilt_expansion_v1",
        score=8,
        minimum_score=8,
        trigger="squeeze_release",
        evidence=("squeeze_release", "adx_usable"),
        stop_anchor=99.0 if side == "long" else 101.0,
        entry_eligible=True,
        reason="eligible",
        signal_side=side,
    )


def _range(side: str, offset: int) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=1_785_600_000_000 + offset * 300_000,
        reference_price=100.0,
        long_entry=side == "long",
        short_entry=side == "short",
        long_exit=False,
        short_exit=False,
        primary_regime="BREAKOUT",
        state_1m="BREAKOUT",
        state_5m="TREND_UP" if side == "long" else "TREND_DOWN",
        context_15m="TREND_UP" if side == "long" else "TREND_DOWN",
        confidence=0.7,
        structural_direction=side,
        regime_admitted=True,
    )


def _range_with_context(
    side: str,
    offset: int,
    *,
    admitted: bool,
) -> SolLiveDecision:
    return replace(
        _range(side, offset),
        readiness=SignalReadiness(
            side=side,
            conditions_met=3,
            conditions_required=3,
            blockers=(),
            indicators=(
                "DUAL-MTF CHALLENGER CLEAR [REPORT ONLY]"
                if admitted
                else "DUAL-MTF CHALLENGER OPPOSED [REPORT ONLY]",
            ),
            metrics={
                "dual_mtf_context_challenger_admitted": admitted,
                "dual_mtf_context_challenger_authority": "report_only",
            },
        ),
    )


def test_hulk_provider_preserves_both_sides_and_strategy_identity() -> None:
    """Hulk-derived long signals are no longer removed by the legacy short gate."""
    observed = pd.Timestamp("2026-08-01T14:00:00Z")

    intents = build_hulk_bidirectional_intents(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=observed,
        after_decision_time_ms=None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab"),
        decision_builder=lambda *args, **kwargs: (_hulk("long", 0), _hulk("short", 1)),
    )

    assert [(intent.symbol, intent.side) for intent in intents] == [
        ("ETH", "long"),
        ("ETH", "short"),
    ]
    assert {intent.strategy_id for intent in intents} == {
        "hulk_expansion_bidirectional_tuned_v2"
    }
    assert [intent.stop_anchor for intent in intents] == [99.0, 101.0]


def test_range_onset_provider_preserves_both_sides() -> None:
    """Range-onset emits attributed long and short intents for any enabled coin."""
    intents = build_range_onset_bidirectional_intents(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-01T14:00:00Z"),
        after_decision_time_ms=None,
        decision_builder=lambda *args, **kwargs: (
            _range("long", 0),
            _range("short", 1),
        ),
    )

    assert [(intent.symbol, intent.side) for intent in intents] == [
        ("HYPE", "long"),
        ("HYPE", "short"),
    ]
    assert {intent.strategy_id for intent in intents} == {
        "range_onset_bidirectional_v1"
    }


def test_explicit_dual_mtf_policy_withholds_only_opposed_range_entries() -> None:
    """The configured ETH rule is symmetric and preserves clear source entries."""
    batch = collect_range_onset_bidirectional_intents(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-01T14:00:00Z"),
        after_decision_time_ms=None,
        entry_context_policies={"ETH": "dual_mtf_not_opposed"},
        decision_builder=lambda *args, **kwargs: (
            _range_with_context("long", 0, admitted=False),
            _range_with_context("long", 1, admitted=True),
            _range_with_context("short", 2, admitted=False),
            _range_with_context("short", 3, admitted=True),
        ),
    )

    assert [(intent.symbol, intent.side) for intent in batch.intents] == [
        ("ETH", "long"),
        ("ETH", "short"),
    ]
    assert [evaluation.eligible for evaluation in batch.evaluations] == [
        False,
        True,
        False,
        True,
    ]
    assert batch.evaluations[0].reason == "entry_context_dual_mtf_opposed"
    assert batch.evaluations[0].readiness.conditions_met == 3
    assert batch.evaluations[0].readiness.conditions_required == 4
    assert batch.evaluations[0].readiness.blockers == ("dual_mtf_context_opposed",)
    assert batch.evaluations[1].readiness.conditions_met == 4
    assert (
        batch.evaluations[1].readiness.metrics["entry_context_policy"]
        == "dual_mtf_not_opposed"
    )


def test_range_provider_preserves_raw_exit_when_entry_context_is_blocked() -> None:
    """Entry admission must not suppress the researched raw-cross exit."""
    decision = replace(
        _range_with_context("short", 0, admitted=False),
        short_entry=False,
        long_exit=True,
    )

    batch = collect_range_onset_bidirectional_intents(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-08-01T14:00:00Z"),
        after_decision_time_ms=None,
        entry_context_policies={"ETH": "dual_mtf_not_opposed"},
        decision_builder=lambda *args, **kwargs: (decision,),
    )

    assert batch.intents == ()
    assert batch.evaluations[0].exit_sides == frozenset({"long"})
    assert batch.evaluations[0].exit_reason == "range_onset_signal"


def test_hulk_provider_exposes_non_entry_score_and_indicator_readiness() -> None:
    """A completed Hulk hold remains visible with exact setup evidence."""
    hold = HulkSmashLiveDecision(
        decision_time_ms=1_785_600_000_000,
        bar_open_at=pd.Timestamp("2026-08-01T12:00:00Z"),
        reference_price=100.0,
        open_price=99.5,
        high_price=100.5,
        low_price=99.0,
        volume=10.0,
        candidate="none",
        score=3,
        minimum_score=8,
        trigger="none",
        evidence=("adx_usable",),
        stop_anchor=None,
        entry_eligible=False,
        reason="no_trigger",
        signal_side="long",
        readiness=SignalReadiness(
            side="short",
            conditions_met=4,
            conditions_required=6,
            blockers=("awaiting_squeeze_release", "volume_not_above_1x"),
            indicators=("ADX 21.4/18.0", "VOLUME 0.92x", "SQUEEZE ON"),
        ),
    )

    batch = collect_hulk_bidirectional_intents(
        pd.DataFrame(),
        symbol="BTC",
        observed_at=pd.Timestamp("2026-08-01T14:00:00Z"),
        after_decision_time_ms=None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab"),
        decision_builder=lambda *args, **kwargs: (hold,),
    )

    assert batch.intents == ()
    evaluation = batch.evaluations[0]
    assert evaluation.decision_action == "hold"
    assert evaluation.reason == "no_trigger"
    assert evaluation.score == 3
    assert evaluation.minimum_score == 8
    assert evaluation.readiness.fraction == 4 / 6
    assert evaluation.side == "short"


def test_range_provider_exposes_cross_distance_and_regime_readiness() -> None:
    """A range hold reports exact regime and SMA-cross proximity inputs."""
    hold = SolLiveDecision(
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        long_entry=False,
        short_entry=False,
        long_exit=False,
        short_exit=False,
        primary_regime="RANGE",
        state_1m="RANGE",
        state_5m="TREND_UP",
        context_15m="TREND_UP",
        confidence=0.62,
        structural_direction="neutral",
        regime_admitted=False,
        readiness=SignalReadiness(
            side="long",
            conditions_met=2,
            conditions_required=3,
            blockers=("5m_regime_not_admitted",),
            indicators=("SMA GAP +1.8bps", "5m RANGE NO", "RAW CROSS NONE"),
        ),
    )

    batch = collect_range_onset_bidirectional_intents(
        pd.DataFrame(),
        symbol="SOL",
        observed_at=pd.Timestamp("2026-08-01T14:00:00Z"),
        after_decision_time_ms=None,
        decision_builder=lambda *args, **kwargs: (hold,),
    )

    assert batch.intents == ()
    evaluation = batch.evaluations[0]
    assert evaluation.reason == "regime_not_admitted"
    assert evaluation.primary_regime == "RANGE"
    assert evaluation.context_15m == "TREND_UP"
    assert evaluation.confidence == 0.62
    assert "SMA GAP +1.8bps" in evaluation.readiness.indicators


def test_provider_evaluation_rejects_invalid_market_evidence() -> None:
    """Malformed provider telemetry cannot enter the authoritative ledger."""
    with pytest.raises(ValueError, match="reference_price"):
        ProviderEvaluation(
            strategy_id="fixture",
            symbol="BTC",
            decision_time_ms=1,
            reference_price=float("nan"),
            decision_action="hold",
            eligible=False,
            reason="fixture_hold",
            side=None,
            readiness=SignalReadiness(
                side=None,
                conditions_met=0,
                conditions_required=1,
                blockers=("fixture",),
                indicators=("FIXTURE",),
            ),
        )
