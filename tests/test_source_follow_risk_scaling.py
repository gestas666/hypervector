"""Causal source-subtype allocation profiles."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research import source_follow_risk_scaling as risk_scaling
from hypervector.research.source_follow_portfolio_models import SourceSignal
from hypervector.research.source_follow_risk_scaling import (
    apply_source_sizing_profile,
    source_sizing_summary,
)


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"],
                utc=True,
            ),
            "secondary_code": ["TD_WEAK_CHOPPY", "TD_STRONG_HIGH_VOL"],
        }
    )


def _signals() -> tuple[SourceSignal, ...]:
    return (
        SourceSignal("2026-01-01T00:00:00+00:00"),
        SourceSignal("2026-01-01T00:05:00+00:00"),
    )


def test_weak_choppy_profile_halves_size_without_deleting_signals() -> None:
    """The challenger must scale only the explicit weak/choppy subtype."""
    scaled = apply_source_sizing_profile(
        _signals(),
        "weak_choppy_half",
        _labels(),
    )

    assert len(scaled) == 2
    assert scaled[0].allocation_multiplier == 0.5
    assert scaled[1].allocation_multiplier == 1.0
    assert [signal.decision_time_utc for signal in scaled] == [
        signal.decision_time_utc for signal in _signals()
    ]
    assert source_sizing_summary(scaled) == {"half_size": 1, "full_size": 1}


def test_weak_choppy_profile_fails_on_missing_exact_source_label() -> None:
    """Sizing must not silently reuse a stale source subtype."""
    labels = _labels().iloc[:1]

    with pytest.raises(ValueError, match="missing exact source labels"):
        apply_source_sizing_profile(_signals(), "weak_choppy_half", labels)


def test_uniform_profile_preserves_signals_without_source_labels() -> None:
    """The historical control must remain independent of subtype evidence."""
    signals = _signals()

    assert apply_source_sizing_profile(signals, "uniform", None) == signals


def test_maker_decisions_receive_exact_weak_choppy_multiplier() -> None:
    """Maker decision annotations must join the same causal available timestamp."""
    decisions = pd.DataFrame(
        {
            "entry_direction": [None, "short", None, "short"],
            "decision_kind": [
                "shared_rearm",
                "shared_entry",
                "shared_rearm",
                "shared_entry",
            ],
        },
        index=pd.to_datetime(
            [
                "2025-12-31T23:58:55Z",
                "2025-12-31T23:59:00Z",
                "2026-01-01T00:03:55Z",
                "2026-01-01T00:04:00Z",
            ],
            utc=True,
        ),
    )

    assert hasattr(risk_scaling, "annotate_maker_decisions_with_source_sizing")
    scaled = risk_scaling.annotate_maker_decisions_with_source_sizing(
        decisions, _labels()
    )

    assert scaled["entry_allocation_multiplier"].tolist() == [1.0, 0.5, 1.0, 1.0]
    assert scaled.drop(columns="entry_allocation_multiplier").equals(decisions)
