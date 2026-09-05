"""Predeclared portfolio cadence-review clock contracts."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

import hypervector.research.cohort_improvement_digest as digest
from hypervector.research.cohort_improvement_history import material_state_sha256


def test_clock_progress_does_not_flood_material_history() -> None:
    """Elapsed countdown progress must not create durable research events."""
    first = {"cadence_review_clock": _clock(elapsed=3_600.0)}
    second = {"cadence_review_clock": _clock(elapsed=3_720.0)}

    assert material_state_sha256(first) == material_state_sha256(second)


def test_clock_review_transition_remains_material_history() -> None:
    """Crossing the frozen threshold must remain a durable research event."""
    monitoring = {"cadence_review_clock": _clock(elapsed=3_600.0)}
    due = {"cadence_review_clock": _clock(elapsed=14 * 24 * 60 * 60)}
    due["cadence_review_clock"].update(
        {"status": "review_due", "review_required": True}
    )

    assert material_state_sha256(monitoring) != material_state_sha256(due)


def test_route_clock_progress_does_not_flood_material_history() -> None:
    """Per-route countdown movement must not append routine history events."""
    first = {"route_cadence_review_clocks": {"route|BTC": _clock(elapsed=3_600.0)}}
    second = {"route_cadence_review_clocks": {"route|BTC": _clock(elapsed=3_720.0)}}

    assert material_state_sha256(first) == material_state_sha256(second)


def test_complete_fourteen_day_zero_entry_window_requires_review() -> None:
    """Complete evidence must activate the frozen zero-entry review trigger."""
    module_name = "hypervector.research.cohort_cadence_review_clock"
    assert importlib.util.find_spec(module_name) is not None, (
        "cadence review clock module is required"
    )
    module = importlib.import_module(module_name)

    result = module.build_cadence_review_clock(_audit(days=14), _trigger())

    assert result["status"] == "review_due"
    assert result["review_required"] is True
    assert result["action"] == "cadence_deviation_investigation"
    assert result["automatic_live_change"] is False
    assert result["execution_authority"] == "none"


def test_due_clock_prioritizes_review_without_creating_a_live_change() -> None:
    """A due clock must change research priority but never create authority."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    report = {
        "assessment": {"recommendation": "collect_live_execution"},
        "highest_value_next_investigation": {
            "route": "hype|HYPE",
            "experiment": "collect_both_side_live_execution",
        },
        "change_proposals": [],
    }
    overrides = {
        "review_triggers": {"zero_entry": _trigger()},
        "evidence": [{"path": "baseline.json"}],
    }

    updated = module.attach_cadence_review_clock(report, _audit(days=14), overrides)

    assert updated["assessment"]["recommendation"] == (
        "run_predeclared_cadence_deviation_investigation"
    )
    assert updated["highest_value_next_investigation"] == {
        "route": "portfolio",
        "experiment": "cadence_deviation_investigation",
        "why_now": "complete_zero_entry_review_threshold_reached",
        "automatic_live_change": False,
    }
    assert updated["change_proposals"] == []


def test_monitor_wrapper_reads_source_bound_trigger_from_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The monitor wrapper must attach the clock from validated digest inputs."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    base = {
        "assessment": {"recommendation": "collect_live_execution"},
        "highest_value_next_investigation": {"route": "hype|HYPE"},
        "change_proposals": [],
    }
    monkeypatch.setattr(
        module,
        "build_continuous_improvement_report",
        lambda checkpoint, digest: dict(base),
    )
    checkpoint = {"audit": _audit(days=14)}
    digest = {
        "research_decision_overrides": {
            "review_triggers": {"zero_entry": _trigger()},
            "evidence": [{"path": "baseline.json"}],
        }
    }

    report = module.build_monitored_improvement_report(checkpoint, digest)

    assert report["cadence_review_clock"]["status"] == "review_due"
    assert report["highest_value_next_investigation"]["experiment"] == (
        "cadence_deviation_investigation"
    )


def test_digest_preserves_review_trigger_and_its_frozen_source() -> None:
    """Validated overrides must carry the exact trigger into the monitor layer."""
    payload = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "review_triggers": {"zero_entry": _trigger()},
        "evidence": [{"path": "baseline.json"}],
    }

    _, summary = digest._apply_experiment_overrides([], payload)

    assert summary["review_triggers"] == payload["review_triggers"]
    assert summary["review_trigger_evidence"] == [{"path": "baseline.json"}]


def test_monitor_uses_the_cadence_aware_report_wrapper() -> None:
    """The running monitor seam must call the cadence-aware report builder."""
    script = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"
    spec = importlib.util.spec_from_file_location("cadence_monitor_probe", script)
    assert spec is not None and spec.loader is not None
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    assert monitor.build_continuous_improvement_report.__module__ == (
        "hypervector.research.cohort_cadence_review_clock"
    )


def test_prethreshold_clock_preserves_the_current_research_priority() -> None:
    """A quiet early window must not manufacture a cadence-deviation finding."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    report = {
        "assessment": {"recommendation": "collect_live_execution"},
        "highest_value_next_investigation": {"route": "hype|HYPE"},
        "change_proposals": [],
    }
    overrides = {
        "review_triggers": {"zero_entry": _trigger()},
        "evidence": [{"path": "baseline.json"}],
    }

    updated = module.attach_cadence_review_clock(report, _audit(days=1), overrides)

    assert updated["cadence_review_clock"]["status"] == "monitoring"
    assert updated["cadence_review_clock"]["review_required"] is False
    assert updated["highest_value_next_investigation"] == {"route": "hype|HYPE"}


def test_observed_lifecycle_closes_the_zero_entry_clock() -> None:
    """A recorded lifecycle must prevent a later zero-entry review trigger."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    audit = _audit(days=14)
    audit["execution"]["closed_trades"] = 1

    result = module.build_cadence_review_clock(audit, _trigger())

    assert result["status"] == "entry_observed"
    assert result["review_required"] is False


def test_route_clocks_use_exact_signal_counts_and_frozen_thresholds() -> None:
    """Each route must become due independently from its own signal evidence."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    audit = _audit(days=8)
    audit["strategy_scorecard"] = {
        "by_provider_symbol": {
            "fast|BTC": {"eligible_signals": 0},
            "observed|HYPE": {"eligible_signals": 1},
            "sparse|BTC": {"eligible_signals": 0},
        }
    }
    triggers = {
        "fast|BTC": _route_trigger(days=7, priority=1),
        "observed|HYPE": _route_trigger(days=7, priority=2),
        "sparse|BTC": _route_trigger(days=28, priority=3),
    }

    clocks = module.build_route_cadence_review_clocks(audit, triggers)

    assert clocks["fast|BTC"]["status"] == "review_due"
    assert clocks["observed|HYPE"]["status"] == "signal_observed"
    assert clocks["sparse|BTC"]["status"] == "monitoring"
    assert clocks["fast|BTC"]["eligible_signals"] == 0
    assert clocks["observed|HYPE"]["eligible_signals"] == 1
    assert clocks["fast|BTC"]["automatic_live_change"] is False


def test_due_route_clock_prioritizes_exact_route_without_live_authority() -> None:
    """A due route must replace vague waiting with one exact investigation."""
    module = importlib.import_module("hypervector.research.cohort_cadence_review_clock")
    report = {
        "assessment": {"recommendation": "collect_live_execution"},
        "highest_value_next_investigation": {"route": "hype|HYPE"},
        "change_proposals": [],
    }
    audit = _audit(days=8)
    audit["strategy_scorecard"] = {
        "by_provider_symbol": {
            "fast|BTC": {"eligible_signals": 0},
            "observed|HYPE": {"eligible_signals": 1},
        }
    }
    overrides = {
        "review_triggers": {
            "zero_entry": _trigger(),
            "route_zero_signal": {
                "fast|BTC": _route_trigger(days=7, priority=1),
                "observed|HYPE": _route_trigger(days=7, priority=2),
            },
        },
        "evidence": [{"path": "baseline.json"}],
    }

    updated = module.attach_cadence_review_clock(report, audit, overrides)

    assert updated["route_cadence_review_clocks"]["fast|BTC"]["review_required"]
    assert updated["highest_value_next_investigation"] == {
        "route": "fast|BTC",
        "experiment": "route_cadence_deviation_investigation",
        "why_now": "exact_route_zero_signal_threshold_reached",
        "automatic_live_change": False,
    }
    assert updated["change_proposals"] == []


def _audit(*, days: int) -> dict[str, object]:
    return {
        "run": {
            "first_observed_at_utc": "2026-08-01T00:00:00+00:00",
            "last_observed_at_utc": f"2026-08-{1 + days:02d}T00:00:00+00:00",
        },
        "execution": {
            "closed_trades": 0,
            "by_asset": {"BTC": {"open_lifecycles": 0}},
        },
        "coverage": {"complete": True, "technical_gaps": []},
    }


def _trigger() -> dict[str, object]:
    return {
        "threshold_seconds": 14 * 24 * 60 * 60,
        "action": "cadence_deviation_investigation",
        "decision_source": "baseline.json",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
        },
    }


def _route_trigger(*, days: int, priority: int) -> dict[str, object]:
    return {
        "threshold_seconds": days * 24 * 60 * 60,
        "priority": priority,
        "action": "route_cadence_deviation_investigation",
        "decision_source": "baseline.json",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
        },
    }


def _clock(*, elapsed: float) -> dict[str, object]:
    threshold = 14 * 24 * 60 * 60
    return {
        "status": "monitoring",
        "review_required": False,
        "action": "cadence_deviation_investigation",
        "threshold_seconds": threshold,
        "elapsed_seconds": elapsed,
        "remaining_seconds": max(float(threshold) - elapsed, 0.0),
        "closed_lifecycles": 0,
        "open_lifecycles": 0,
        "coverage_complete": True,
        "decision_source": "baseline.json",
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }
