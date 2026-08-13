"""Causal annotation contracts for the rebuilt Hulk Trading Brain."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hulk_smash_brain import (
    HulkBrainConfig,
    HulkBrainSizingConfig,
    annotate_hulk_signals,
    apply_hulk_brain_risk_scaling,
    brain_outcomes_from_replay,
    wilson_interval,
)
from hypervector.research.market_cipher_replay import evaluate_market_cipher_replay
from hypervector.research.market_cipher_replay_models import MarketCipherReplayConfig


def _signals(times: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_time_utc": pd.to_datetime(times, utc=True),
            "symbol": ["BTC"] * len(times),
            "candidate": ["hulk_rebuilt_expansion_v1"] * len(times),
            "side": ["long"] * len(times),
            "trigger": ["squeeze_release"] * len(times),
            "evidence": [("squeeze_release", "ema_trend", "adx_usable")] * len(times),
            "eligible": [True] * len(times),
        }
    )


def _outcomes(
    signal_times: list[str],
    exit_times: list[str],
    returns_r: list[float],
    *,
    symbols: list[str] | None = None,
    evidence: list[tuple[str, ...]] | None = None,
) -> pd.DataFrame:
    count = len(signal_times)
    return pd.DataFrame(
        {
            "signal_time_utc": pd.to_datetime(signal_times, utc=True),
            "exit_time_utc": pd.to_datetime(exit_times, utc=True),
            "symbol": symbols or ["BTC"] * count,
            "candidate": ["hulk_rebuilt_expansion_v1"] * count,
            "side": ["long"] * count,
            "trigger": ["squeeze_release"] * count,
            "evidence": evidence
            or [("squeeze_release", "ema_trend", "adx_usable")] * count,
            "net_return_r": returns_r,
        }
    )


def test_wilson_interval_reports_low_support_uncertainty() -> None:
    """A perfect tiny sample must not masquerade as high certainty."""
    lower, upper = wilson_interval(successes=1, total=1, z=1.96)

    assert lower < 0.25
    assert upper > 0.75
    assert wilson_interval(successes=0, total=0) == (0.0, 1.0)


def test_annotation_uses_only_outcomes_resolved_before_decision() -> None:
    """Future and same-timestamp outcomes cannot affect an annotation."""
    signals = _signals(["2026-01-03 00:00", "2026-01-05 00:00"])
    outcomes = _outcomes(
        ["2026-01-01 00:00", "2026-01-02 00:00"],
        ["2026-01-03 00:00", "2026-01-03 00:00"],
        [3.0, -3.0],
    )

    annotated = annotate_hulk_signals(signals, outcomes)

    assert annotated.iloc[0]["brain_raw_support"] == 0
    assert annotated.iloc[0]["brain_score"] == pytest.approx(0.0)
    assert annotated.iloc[1]["brain_raw_support"] == 2
    assert annotated.iloc[1]["brain_score"] == pytest.approx(0.0)


def test_hierarchical_pool_borrows_from_similar_not_opposite_signals() -> None:
    """Sparse exact contexts borrow weighted evidence within their direction."""
    signals = _signals(["2026-02-01 00:00"])
    signals.loc[0, "symbol"] = "SOL"
    outcomes = _outcomes(
        ["2026-01-01 00:00", "2026-01-02 00:00", "2026-01-03 00:00"],
        ["2026-01-02 00:00", "2026-01-03 00:00", "2026-01-04 00:00"],
        [1.0, 2.0, -3.0],
        symbols=["BTC", "BTC", "BTC"],
        evidence=[
            ("squeeze_release", "ema_trend", "adx_usable"),
            ("squeeze_release", "ema_trend", "volume"),
            ("wave_cross", "ema_trend"),
        ],
    )
    outcomes.loc[2, "side"] = "short"

    annotated = annotate_hulk_signals(
        signals,
        outcomes,
        HulkBrainConfig(half_life_days=365.0, minimum_support=2),
    )

    row = annotated.iloc[0]
    assert row["brain_raw_support"] == 2
    assert row["brain_exact_support"] == 0
    assert row["brain_score"] > 0.0
    assert row["brain_supported"]


def test_decay_moves_stale_evidence_toward_neutral() -> None:
    """Old positive history must lose influence instead of decaying to reject."""
    signals = _signals(["2026-02-01 00:00"])
    outcomes = _outcomes(
        ["2025-01-01 00:00"],
        ["2025-01-02 00:00"],
        [3.0],
    )

    fast = annotate_hulk_signals(
        signals,
        outcomes,
        HulkBrainConfig(half_life_days=1.0, neutral_prior_weight=2.0),
    )
    slow = annotate_hulk_signals(
        signals,
        outcomes,
        HulkBrainConfig(half_life_days=1_000.0, neutral_prior_weight=2.0),
    )

    assert fast.iloc[0]["brain_score"] == pytest.approx(0.0, abs=1e-20)
    assert slow.iloc[0]["brain_score"] > 0.0
    assert fast.iloc[0]["brain_annotation"] == "insufficient_support"


def test_outcome_magnitude_is_bounded_and_after_friction() -> None:
    """One extreme return cannot dominate the bounded memory estimate."""
    signals = _signals(["2026-02-01 00:00"])
    ordinary = _outcomes(["2026-01-01 00:00"], ["2026-01-02 00:00"], [3.0])
    extreme = ordinary.copy()
    extreme["net_return_r"] = 3_000.0
    config = HulkBrainConfig(half_life_days=365.0, return_clip_r=3.0)

    normal_row = annotate_hulk_signals(signals, ordinary, config).iloc[0]
    extreme_row = annotate_hulk_signals(signals, extreme, config).iloc[0]

    assert extreme_row["brain_score"] == pytest.approx(normal_row["brain_score"])


def test_brain_is_annotation_only_and_preserves_signal_identity() -> None:
    """Brain output may not delete, reorder, or mutate execution eligibility."""
    signals = _signals(["2026-01-05 00:00", "2026-01-06 00:00"])
    signals.loc[1, "eligible"] = False
    original = signals.copy(deep=True)

    annotated = annotate_hulk_signals(signals, _outcomes([], [], []))

    pd.testing.assert_frame_equal(signals, original)
    assert annotated[original.columns.tolist()].equals(original)
    assert annotated["eligible"].tolist() == [True, False]
    assert annotated["brain_execution_authority"].eq("none").all()


def test_replay_conversion_uses_net_after_friction_return() -> None:
    """Brain magnitude must use replay net PnL divided by actual risk budget."""
    index = pd.date_range("2026-01-01", periods=3, freq="30min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.5],
            "high": [100.1, 100.5, 100.8],
            "low": [99.9, 99.9, 100.4],
            "close": [100.0, 100.4, 100.7],
            "funding_rate": [0.0, 0.0, 0.0],
            "wave_cross": [0, 0, 0],
        },
        index=index,
    )
    signals = _signals([index[0].isoformat()])
    signals["stop_anchor"] = 99.99
    signals["score"] = 8
    report = evaluate_market_cipher_replay(
        {"BTC": bars},
        signals,
        MarketCipherReplayConfig(
            initial_equity=10_000.0,
            risk_fraction=0.005,
            leverage=5.0,
            target_r_multiple=3.0,
        ),
    )

    outcomes = brain_outcomes_from_replay(report, signals)

    assert len(outcomes) == 1
    assert outcomes.iloc[0]["net_return_r"] == pytest.approx(
        report.trades[0].net_pnl_usd / report.trades[0].risk_budget_usd
    )
    assert outcomes.iloc[0]["exit_time_utc"] == pd.Timestamp(
        report.trades[0].exit_time_utc
    )


def test_replay_conversion_rejects_ambiguous_signal_identity() -> None:
    """Duplicate contexts must fail rather than attach an arbitrary memory."""
    index = pd.date_range("2026-01-01", periods=3, freq="30min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0] * 3,
            "high": [100.1] * 3,
            "low": [99.9] * 3,
            "close": [100.0] * 3,
            "funding_rate": [0.0] * 3,
            "wave_cross": [0] * 3,
        },
        index=index,
    )
    signals = _signals([index[0].isoformat()])
    signals["stop_anchor"] = 99.0
    signals["score"] = 8
    report = evaluate_market_cipher_replay({"BTC": bars}, signals)
    duplicated = pd.concat([signals, signals], ignore_index=True)

    with pytest.raises(ValueError, match="ambiguous signal identity"):
        brain_outcomes_from_replay(report, duplicated)


def test_brain_risk_scaling_is_continuous_and_never_filters() -> None:
    """Supported scores scale bounded risk while unsupported rows stay neutral."""
    annotated = _signals(["2026-01-05 00:00", "2026-01-06 00:00", "2026-01-07 00:00"])
    annotated["brain_score"] = [0.2, -0.4, 1.0]
    annotated["brain_supported"] = [True, True, False]
    original_eligible = annotated["eligible"].copy()

    scaled = apply_hulk_brain_risk_scaling(
        annotated,
        HulkBrainSizingConfig(
            score_gain=2.0,
            minimum_risk_multiplier=0.5,
            maximum_risk_multiplier=1.5,
        ),
    )

    assert scaled["risk_multiplier"].tolist() == pytest.approx([1.4, 0.5, 1.0])
    assert scaled["eligible"].equals(original_eligible)
    assert scaled["brain_sizing_execution_authority"].eq("none").all()


@pytest.mark.parametrize(
    "column",
    ["signal_time_utc", "symbol", "candidate", "side", "trigger", "evidence"],
)
def test_missing_required_context_fails_explicitly(column: str) -> None:
    """Missing context cannot silently become a neutral fingerprint."""
    signals = _signals(["2026-01-05 00:00"]).drop(columns=column)

    with pytest.raises(ValueError, match="missing columns"):
        annotate_hulk_signals(signals, _outcomes([], [], []))
