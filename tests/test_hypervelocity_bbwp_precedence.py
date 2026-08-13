"""Report-only BBWP range-precedence tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_1m_trend_breakout_confirmation,
    apply_5m_bbwp_range_precedence,
    apply_5m_compression_release_confirmation,
    apply_breakout_onset_confirmation,
    apply_fresh_opposed_context_confirmation,
    apply_regime_entry_age_limit,
    apply_weak_opposed_strength_delay,
)


def test_breakout_onset_confirms_only_first_row_after_hard_range() -> None:
    index = pd.date_range("2026-01-01", periods=6, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "state_1m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_UP",
            ],
            "state_5m": [
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
            ],
            "structural_direction": [None, "long", "long", None, "long", "long"],
            "entry_direction": [None] * 6,
            "reason": ["5m_bbwp_compression_range"]
            + ["5m_breakout_awaiting_1m_confirmation"] * 2
            + ["5m_bbwp_compression_range"]
            + ["5m_breakout_awaiting_1m_confirmation"] * 2,
            "bbwp_5m_hard_range": [True, False, False, True, False, False],
        },
        index=index,
    )

    result = apply_breakout_onset_confirmation(decisions)

    assert result["entry_direction"].tolist() == [
        None,
        "long",
        None,
        None,
        None,
        None,
    ]
    assert result["breakout_confirmed_at_range_onset"].tolist() == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert result["reason"].iloc[1] == "5m_breakout_confirmed_at_range_onset"
    assert decisions["entry_direction"].isna().all()


def test_1m_trend_confirms_only_same_direction_5m_breakout() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "primary_regime": ["BREAKOUT", "BREAKOUT", "BREAKOUT", "TREND_UP"],
            "state_1m": ["TREND_UP", "RANGE", "TREND_DOWN", "TREND_UP"],
            "state_5m": ["BREAKOUT", "BREAKOUT", "BREAKOUT", "TREND_UP"],
            "structural_direction": ["long", "short", "long", "long"],
            "entry_direction": [None, None, None, "long"],
            "reason": [
                "5m_breakout_awaiting_1m_confirmation",
                "5m_breakout_awaiting_1m_confirmation",
                "5m_breakout_awaiting_1m_confirmation",
                "5m_primary_trend",
            ],
        },
        index=index,
    )

    result = apply_1m_trend_breakout_confirmation(decisions)

    assert result["entry_direction"].iloc[[0, 3]].tolist() == ["long", "long"]
    assert result["entry_direction"].iloc[1:3].isna().all()
    assert result["breakout_confirmed_by_1m_trend"].tolist() == [
        True,
        False,
        False,
        False,
    ]
    assert result["reason"].tolist() == [
        "5m_breakout_confirmed_by_1m_trend",
        "5m_breakout_awaiting_1m_confirmation",
        "5m_breakout_awaiting_1m_confirmation",
        "5m_primary_trend",
    ]
    assert decisions["entry_direction"].isna().iloc[:3].all()


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP", "BREAKOUT", "TREND_DOWN"],
            "state_5m": ["TREND_UP", "BREAKOUT", "TREND_DOWN"],
            "structural_direction": ["long", "long", "short"],
            "entry_direction": ["long", "long", "short"],
            "reason": ["5m_primary_trend"] * 3,
            "bbwp_percentile": [20.0, 30.0, 30.0],
        },
        index=index,
    )
    context = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP", "BREAKOUT", "TREND_DOWN"],
            "bbwp_percentile": [20.0, 10.0, 30.0],
        },
        index=index,
    )
    return decisions, context


def test_hard_precedence_masks_only_compressed_5m_trends() -> None:
    decisions, context = _frames()

    result = apply_5m_bbwp_range_precedence(decisions, context, threshold=25.0)

    assert result["primary_regime"].tolist() == [
        "RANGE",
        "BREAKOUT",
        "TREND_DOWN",
    ]
    assert pd.isna(result["structural_direction"].iloc[0])
    assert result["structural_direction"].iloc[1:].tolist() == ["long", "short"]
    assert pd.isna(result["entry_direction"].iloc[0])
    assert result["entry_direction"].iloc[1:].tolist() == ["long", "short"]
    assert result["bbwp_5m_hard_range"].tolist() == [True, False, False]
    assert result["reason"].iloc[0] == "5m_bbwp_compression_range"


def test_hard_precedence_does_not_mutate_control_decisions() -> None:
    decisions, context = _frames()

    apply_5m_bbwp_range_precedence(decisions, context, threshold=25.0)

    assert decisions["primary_regime"].iloc[0] == "TREND_UP"
    assert decisions["entry_direction"].iloc[0] == "long"


def test_hard_precedence_requires_aligned_context() -> None:
    decisions, context = _frames()

    with pytest.raises(ValueError, match="same index"):
        apply_5m_bbwp_range_precedence(
            decisions,
            context.iloc[:-1],
            threshold=25.0,
        )


def test_hard_precedence_rejects_invalid_threshold() -> None:
    decisions, context = _frames()

    with pytest.raises(ValueError, match="threshold"):
        apply_5m_bbwp_range_precedence(decisions, context, threshold=101.0)


def test_recovery_delay_masks_entry_but_preserves_structure() -> None:
    decisions, _ = _frames()

    result = apply_1m_bbwp_recovery_delay(
        decisions,
        threshold=25.0,
        minimum_age_bars=2,
    )

    assert result["entry_direction"].isna().iloc[:2].all()
    assert result["entry_direction"].iloc[2] == "short"
    assert result["structural_direction"].tolist() == ["long", "long", "short"]
    assert result["primary_regime"].tolist() == decisions["primary_regime"].tolist()
    assert result["bbwp_1m_compression_age_bars"].tolist() == [0.0, 1.0, 2.0]


def test_recovery_delay_allows_entries_before_any_observed_compression() -> None:
    decisions, _ = _frames()
    decisions["bbwp_percentile"] = [50.0, 50.0, 50.0]

    result = apply_1m_bbwp_recovery_delay(
        decisions,
        threshold=25.0,
        minimum_age_bars=6,
    )

    assert result["entry_direction"].tolist() == ["long", "long", "short"]
    assert result["bbwp_1m_compression_age_bars"].isna().all()


def test_recovery_delay_rejects_negative_age() -> None:
    decisions, _ = _frames()

    with pytest.raises(ValueError, match="minimum_age_bars"):
        apply_1m_bbwp_recovery_delay(
            decisions,
            threshold=25.0,
            minimum_age_bars=-1,
        )


def test_regime_entry_age_limit_is_causal_and_entry_only() -> None:
    """Late regime age masks entries without rewriting canonical state."""
    index = pd.date_range("2026-01-01", periods=6, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "primary_regime": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "state_5m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "structural_direction": ["long", "long", "long", None, "short", "short"],
            "entry_direction": ["long", "long", "long", None, "short", "short"],
        },
        index=index,
    )

    result = apply_regime_entry_age_limit(decisions, maximum_age_exclusive=2)
    prefix = apply_regime_entry_age_limit(decisions.iloc[:4], maximum_age_exclusive=2)

    assert result["regime_age_5m_bars"].tolist() == [0, 1, 2, 0, 0, 1]
    assert result["regime_entry_age_blocked"].tolist() == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    assert pd.isna(result["entry_direction"].iloc[2])
    assert result["state_5m"].tolist() == decisions["state_5m"].tolist()
    assert (
        result["structural_direction"].tolist()
        == decisions["structural_direction"].tolist()
    )
    pd.testing.assert_frame_equal(result.iloc[:4], prefix)


def test_fresh_opposed_context_confirmation_delays_only_new_reversal() -> None:
    """Fresh counter-context entries wait while structure remains unchanged."""
    index = pd.date_range("2026-01-01", periods=7, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "state_5m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
                "RANGE",
                "TREND_UP",
            ],
            "context_15m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "structural_direction": [
                "long",
                "long",
                "short",
                "short",
                "short",
                None,
                "long",
            ],
            "entry_direction": [
                "long",
                "long",
                "short",
                "short",
                "short",
                None,
                "long",
            ],
        },
        index=index,
    )

    result = apply_fresh_opposed_context_confirmation(
        decisions,
        confirmation_bars=1,
    )
    prefix = apply_fresh_opposed_context_confirmation(
        decisions.iloc[:5],
        confirmation_bars=1,
    )

    assert result["fresh_opposed_context_wait"].tolist() == [
        False,
        False,
        True,
        False,
        False,
        False,
        True,
    ]
    assert result["entry_direction"].dropna().tolist() == [
        "long",
        "long",
        "short",
        "short",
    ]
    assert result["entry_direction"].isna().tolist() == [
        False,
        False,
        True,
        False,
        False,
        True,
        True,
    ]
    assert (
        result["structural_direction"].tolist()
        == decisions["structural_direction"].tolist()
    )
    assert result["state_5m"].tolist() == decisions["state_5m"].tolist()
    pd.testing.assert_frame_equal(result.iloc[:5], prefix)


def test_fresh_opposed_context_confirmation_rejects_invalid_age() -> None:
    decisions = pd.DataFrame(
        {
            "state_5m": ["TREND_UP"],
            "context_15m": ["TREND_UP"],
            "entry_direction": ["long"],
        },
        index=pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC"),
    )

    with pytest.raises(ValueError, match="confirmation_bars"):
        apply_fresh_opposed_context_confirmation(
            decisions,
            confirmation_bars=0,
        )


def test_weak_opposed_strength_delay_preserves_regimes_and_aligned_entries() -> None:
    """Only weak counter-context entries wait for stronger causal evidence."""
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "state_5m": ["TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN", "RANGE"],
            "context_15m": ["TREND_UP", "TREND_DOWN", "TREND_UP", "TREND_UP", "RANGE"],
            "structural_direction": ["long", "long", "short", "short", None],
            "entry_direction": ["long", "long", "short", "short", None],
            "regime_strength_percentile": [20.0, 49.9, 50.0, 80.0, float("nan")],
        },
        index=index,
    )

    result = apply_weak_opposed_strength_delay(
        decisions,
        minimum_strength_percentile=50.0,
    )

    assert result["weak_opposed_strength_wait"].tolist() == [
        False,
        True,
        False,
        False,
        False,
    ]
    assert result["entry_direction"].dropna().tolist() == [
        "long",
        "short",
        "short",
    ]
    assert result["state_5m"].tolist() == decisions["state_5m"].tolist()
    assert (
        result["structural_direction"].tolist()
        == decisions["structural_direction"].tolist()
    )


def test_weak_opposed_strength_delay_rejects_invalid_threshold() -> None:
    decisions = pd.DataFrame(
        {
            "context_15m": ["TREND_UP"],
            "entry_direction": ["short"],
            "regime_strength_percentile": [20.0],
        },
        index=pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC"),
    )

    with pytest.raises(ValueError, match="minimum_strength_percentile"):
        apply_weak_opposed_strength_delay(
            decisions,
            minimum_strength_percentile=101.0,
        )


def test_compression_release_confirmation_delays_then_restores_trend() -> None:
    """One 5m release interval is causal TRANSITION, then base state returns."""
    index = pd.date_range("2026-01-01", periods=8, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "primary_regime": ["RANGE", "RANGE"] + ["TREND_UP"] * 6,
            "state_5m": ["RANGE", "RANGE"] + ["TREND_UP"] * 6,
            "structural_direction": [None, None] + ["long"] * 6,
            "entry_direction": [None, None] + ["long"] * 6,
            "reason": ["compression", "compression"] + ["trend"] * 6,
            "bbwp_5m_hard_range": [True, True] + [False] * 6,
        },
        index=index,
    )

    result = apply_5m_compression_release_confirmation(decisions, confirmation_bars=5)
    prefix = apply_5m_compression_release_confirmation(
        decisions.iloc[:7], confirmation_bars=5
    )

    assert result["bbwp_5m_release_age_bars"].tolist() == [
        0.0,
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
    ]
    assert result["bbwp_5m_release_wait"].tolist() == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert result["primary_regime"].iloc[2:7].eq("TRANSITION").all()
    assert result["entry_direction"].iloc[2:7].isna().all()
    assert result["primary_regime"].iloc[7] == "TREND_UP"
    assert result["entry_direction"].iloc[7] == "long"
    pd.testing.assert_frame_equal(result.iloc[:7], prefix)
