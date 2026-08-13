"""Tests for causal, report-only range-onset context challengers."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.range_onset_context_challenger import (
    BASELINE_CANDIDATE,
    build_context_signal_variants,
)


def _evidence() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    signals = pd.DataFrame(
        {
            "long_entry": [True, False, True, False],
            "short_entry": [False, True, False, False],
            "long_exit": False,
            "short_exit": False,
        },
        index=index,
    )
    regimes = pd.DataFrame(
        {"state_1m": ["TREND_DOWN", "TREND_DOWN", "TREND_UP", "RANGE"]},
        index=index,
    )
    components = pd.DataFrame(
        {
            "ema_21_55_direction": [-1.0, -1.0, 1.0, 1.0],
            "sma_100_200_direction": [-1.0, -1.0, -1.0, 1.0],
            "cipher_a_direction": [-1.0, -1.0, 1.0, 1.0],
            "harsi_direction": [-1.0, -1.0, 1.0, 1.0],
            "mtf_5m_bias": [-3.0, -3.0, -3.0, 3.0],
            "mtf_15m_bias": [-3.0, -3.0, 3.0, 3.0],
            "trend_slope_bps": [-2.0, -2.0, 2.0, 2.0],
        },
        index=index,
    )
    return signals, regimes, components


def test_context_variants_preserve_baseline_and_apply_symmetric_challengers() -> None:
    """Predeclared challengers must treat equivalent long/short evidence alike."""
    signals, regimes, components = _evidence()

    variants = build_context_signal_variants(signals, regimes, components)

    assert tuple(variants) == (
        BASELINE_CANDIDATE,
        "component_alignment_gte_neg05",
        "dual_mtf_not_opposed",
        "state_1m_not_opposed",
    )
    baseline = variants[BASELINE_CANDIDATE]
    assert baseline["long_entry"].tolist() == [True, False, True, False]
    assert baseline["short_entry"].tolist() == [False, True, False, False]
    component = variants["component_alignment_gte_neg05"]
    assert component["long_entry"].tolist() == [False, False, True, False]
    assert component["short_entry"].tolist() == [False, True, False, False]
    mtf = variants["dual_mtf_not_opposed"]
    assert mtf["long_entry"].tolist() == [False, False, True, False]
    assert mtf["short_entry"].tolist() == [False, True, False, False]
    one_minute = variants["state_1m_not_opposed"]
    assert one_minute["long_entry"].tolist() == [False, False, True, False]
    assert one_minute["short_entry"].tolist() == [False, True, False, False]


def test_context_variants_emit_exact_decision_time_annotations() -> None:
    """The live ETH-style fully opposed long must score minus one without lookahead."""
    signals, regimes, components = _evidence()

    baseline = build_context_signal_variants(signals, regimes, components)[
        BASELINE_CANDIDATE
    ]

    assert baseline["context_component_alignment_score"].iloc[0] == pytest.approx(-1.0)
    assert bool(baseline["context_dual_mtf_opposed"].iloc[0])
    assert bool(baseline["context_state_1m_opposed"].iloc[0])
    assert baseline["context_component_alignment_score"].iloc[1] == pytest.approx(1.0)


def test_context_variants_fail_on_missing_entry_evidence() -> None:
    """A challenger must not silently admit or reject an unscored source entry."""
    signals, regimes, components = _evidence()
    components.loc[components.index[0], "mtf_15m_bias"] = float("nan")

    with pytest.raises(ValueError, match="context evidence unavailable at 1 entry"):
        build_context_signal_variants(signals, regimes, components)


def test_context_variants_reject_misaligned_inputs() -> None:
    """All annotations must describe the exact source decision row."""
    signals, regimes, components = _evidence()

    with pytest.raises(ValueError, match="same index"):
        build_context_signal_variants(signals, regimes.iloc[1:], components)
