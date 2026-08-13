"""Continuous production replay contract for the frozen source session."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_session_continuous_replay.py")
    assert path.is_file(), "source-session continuous replay script is missing"
    spec = importlib.util.spec_from_file_location("session_continuous", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("source-session continuous replay script could not load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact(
    path: Path,
    recipe: str,
    *,
    family: str = "btc_selected_sizing_surface_v1",
    entry_family: str = "source-follow-all-day-confidence-70",
) -> None:
    path.write_text(
        json.dumps(
            {
                "candidate_family": family,
                "entry_family": entry_family,
                "fresh": {
                    "candidates": {
                        "alloc50_lev30": {"event_outcomes": [{"recipe_id": recipe}]}
                    }
                },
            }
        )
    )


def test_session_continuous_contract_is_exact_35_percent_30x() -> None:
    """The validation target must match the promising later-window contract."""
    module = _load_script()
    contract = module.experiment_contract("alloc35_lev30")

    assert contract["source_session_utc"] == "[06:00,15:00)"
    assert contract["session_clock"] == "decision_time_utc"
    assert contract["margin_fraction"] == 0.35
    assert contract["leverage"] == 30.0
    assert contract["gross_margin_target_pct"] == 8.0
    assert contract["execution_authority"] == "none"


def test_session_range_floor_control_preserves_session_and_risk() -> None:
    """Removing the range floor must not alter clock, sizing, or authority."""
    module = _load_script()

    contract = module.experiment_contract("alloc35_lev30", 0.0)

    assert contract["candidate"] == (
        "source_follow_session_06_15_minrange0_continuous_v1"
    )
    assert contract["minimum_signal_range_bps"] == 0.0
    assert contract["source_session_utc"] == "[06:00,15:00)"
    assert contract["margin_fraction"] == 0.35
    assert contract["leverage"] == 30.0
    assert contract["execution_authority"] == "none"


def test_session_continuous_accepts_only_all_day_source_artifacts(
    tmp_path: Path,
) -> None:
    """Decision-time filtering requires the unfiltered all-day source family."""
    module = _load_script()
    session = tmp_path / "session.json"
    all_day = tmp_path / "all-day.json"
    _artifact(all_day, "follow_td_all_day_conf70")
    _artifact(
        session,
        "follow_td_session_06_15_conf70",
        family="btc_allocation_leverage_surface_v1",
        entry_family="source-follow-session-06-15-confidence-70",
    )

    module.validate_session_artifact(all_day, "alloc50_lev30")
    with pytest.raises(ValueError, match="all-day source artifact"):
        module.validate_session_artifact(session, "alloc50_lev30")


def test_session_filter_uses_decision_time_half_open_boundary() -> None:
    """05:55 and 15:00 decisions are excluded even if label hours would differ."""
    module = _load_script()
    from hypervector.research.source_follow_portfolio_models import SourceSignal

    signals = tuple(
        SourceSignal(value)
        for value in (
            "2026-01-01T05:55:00+00:00",
            "2026-01-01T06:00:00+00:00",
            "2026-01-01T14:55:00+00:00",
            "2026-01-01T15:00:00+00:00",
        )
    )

    selected = module.decision_session_signals(signals)

    assert [signal.decision_time_utc for signal in selected] == [
        "2026-01-01T06:00:00+00:00",
        "2026-01-01T14:55:00+00:00",
    ]
