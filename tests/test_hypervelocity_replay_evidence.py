from __future__ import annotations

import pandas as pd

from hypervector.research.hypervelocity_replay_evidence import decision_identity


def test_decision_identity_includes_optional_stop_prices() -> None:
    index = pd.date_range("2026-07-28", periods=2, freq="1min", tz="UTC")
    control = pd.DataFrame(
        {
            "entry_direction": ["long", "long"],
            "structural_direction": ["long", "long"],
        },
        index=index,
    )
    stopped = control.assign(entry_stop_price=[99.0, 99.0])

    assert decision_identity(control) != decision_identity(stopped)


def test_decision_identity_is_stable_for_identical_optional_controls() -> None:
    index = pd.date_range("2026-07-28", periods=2, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "entry_direction": ["short", "short"],
            "structural_direction": ["short", "short"],
            "entry_stop_price": [101.0, 101.0],
            "maximum_hold_seconds": [None, None],
        },
        index=index,
    )

    assert decision_identity(decisions) == decision_identity(decisions.copy())
