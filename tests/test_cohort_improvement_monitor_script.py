"""CLI contracts for the rolling portfolio-improvement digest."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"


def test_default_override_is_bound_to_v51_and_immutable_route_evidence() -> None:
    """The v51 override may use only its exact source-bound research decision."""
    module = _load()

    args = module.build_parser().parse_args([])
    payload = json.loads(args.decision_overrides.read_text())

    assert args.decision_overrides.name == (
        "cohort_improvement_decision_overrides_v51.json"
    )
    assert payload["source_profile_id"] == (
        "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
    )
    assert payload["source_profile_fingerprint"] == (
        "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
    )
    route = payload["routes"][
        "hype_breakout_compression_pullback_bidirectional_v1|HYPE"
    ]
    assert route["triage"] == "REVISE"
    assert route["next_experiment"] == "new_mechanic_version_required"
    assert route["decision_source"].endswith(
        "v51-hype-compression-first-window-v1.json"
    )
    assert len(payload["evidence"]) == 1
    assert args.maximum_checkpoint_age_seconds == 180.0


def test_once_publishes_source_bound_report_only_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One refresh must atomically bind the source checkpoint evidence."""
    module = _load()
    checkpoint, output, history, overrides, generated_at = _monitor_files(tmp_path)
    _install_fakes(module, monkeypatch)
    args = _once_args(module, checkpoint, output, history, overrides)

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    persisted = json.loads(output.read_text())
    assert persisted["marker"] == 7
    assert persisted["continuous_improvement"] is True
    assert persisted["source_checkpoint_generated_at_utc"] == generated_at
    assert persisted["evidence"]["checkpoint"]["sha256"]
    assert persisted["evidence"]["decision_overrides"]["sha256"]
    assert persisted["material_state_sha256"]
    assert len(history.read_text().splitlines()) == 1


def test_material_hash_ignores_poll_clock_but_not_research_state() -> None:
    """An unchanged hypothesis cannot create a new material-history event."""
    module = _load()
    first = {
        "source": {"last_observed_at_utc": "2026-08-13T20:00:00Z"},
        "operational_assessment": {"heartbeat_age_seconds": 2.0},
        "evidence_health": {"right_censored_observations": 10},
        "hypothesis_ledger": [{"route": "range|SOL", "status": "being_tested"}],
    }
    second = {
        "source": {"last_observed_at_utc": "2026-08-13T20:02:00Z"},
        "operational_assessment": {"heartbeat_age_seconds": 3.0},
        "evidence_health": {"right_censored_observations": 11},
        "hypothesis_ledger": [{"route": "range|SOL", "status": "being_tested"}],
    }

    assert module._material_digest(first) == module._material_digest(second)
    second["hypothesis_ledger"][0]["status"] = "rejected"
    assert module._material_digest(first) != module._material_digest(second)


def test_material_hash_ignores_live_path_clock_but_keeps_path_assessment() -> None:
    """Routine path maturation must not flood the material hypothesis history."""
    module = _load()
    first = _live_diagnostic_report(10, "insufficient_independent_paths")
    second = _live_diagnostic_report(11, "insufficient_independent_paths")

    assert module._material_digest(first) == module._material_digest(second)
    path = second["live_opportunity_diagnostics"]["routes"][0]
    path["one_blocker_paths"][0]["assessment"] = "robust_report_only_research_lead"
    assert module._material_digest(first) != module._material_digest(second)

    first = _live_diagnostic_report(10, "robust_report_only_research_lead")
    second = _live_diagnostic_report(11, "robust_report_only_research_lead")
    assert module._material_digest(first) == module._material_digest(second)


def _live_diagnostic_report(count: int, assessment: str) -> dict[str, object]:
    path = {
        "assessment": assessment,
        "censored": count,
        "blocker_evaluations": count,
        "independent_resolved": 3,
    }
    return {
        "live_opportunity_diagnostics": {
            "observation_window": {
                "start_utc": "2026-08-13T20:00:00+00:00",
                "end_utc": f"2026-08-13T20:{count:02d}:00+00:00",
                "duration_seconds": float(count * 60),
            },
            "totals": {
                "evaluations": count,
                "eligible_evaluations": 0,
                "directional_evaluations": count,
                "right_censored_observations": count,
            },
            "routes": [
                {
                    "route": "range|SOL",
                    "outcome_evaluations": count,
                    "readiness_evaluations": count,
                    "eligible_evaluations": 0,
                    "blocker_counts": {"gate_absent": count},
                    "one_blocker_paths": [dict(path)],
                }
            ],
            "robust_report_only_leads": [dict(path)]
            if assessment == "robust_report_only_research_lead"
            else [],
        }
    }


def test_failed_once_preserves_last_good_output(tmp_path: Path) -> None:
    """Malformed evidence must fail without replacing the last valid digest."""
    module = _load()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    checkpoint.write_text("not-json")
    output.write_text('{"last":"good"}\n')
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output), "--once"]
    )

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 2
    assert json.loads(output.read_text()) == {"last": "good"}


def test_override_identity_must_match_the_checkpoint_profile() -> None:
    """Decisions from another profile cannot enter the current research queue."""
    module = _load()
    audit = {
        "run": {
            "profile_id": "profile-51",
            "profile_fingerprint": "a" * 64,
        }
    }
    override = {
        "source_profile_id": "profile-old",
        "source_profile_fingerprint": "b" * 64,
    }

    with pytest.raises(ValueError, match="decision override profile identity"):
        module._validate_override_identity(override, audit)


def test_monitor_rejects_nonfinite_poll_interval() -> None:
    """NaN cannot bypass the monitor's positive-interval contract."""
    module = _load()
    args = module.build_parser().parse_args(["--interval-seconds", "nan"])

    with pytest.raises(ValueError, match="interval must be positive and finite"):
        module._validate_loop_args(args)


def test_monitor_rejects_a_stale_checkpoint_document() -> None:
    """A frozen healthy checkpoint cannot masquerade as current evidence."""
    module = _load()
    checkpoint = {"generated_at_utc": "2026-08-13T20:00:00+00:00"}
    observed = datetime(2026, 8, 13, 20, 1, 31, tzinfo=UTC)

    with pytest.raises(ValueError, match="checkpoint is stale"):
        module._validate_checkpoint_freshness(checkpoint, observed, 90.0)


def _monitor_files(tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    overrides = tmp_path / "overrides.json"
    generated_at = datetime.now(UTC).isoformat()
    checkpoint.write_text(json.dumps(_checkpoint(generated_at)))
    overrides.write_text(json.dumps(_overrides()))
    return checkpoint, output, history, overrides, generated_at


def _checkpoint(generated_at: str) -> dict[str, object]:
    return {
        "generated_at_utc": generated_at,
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "audit": {
            "marker": 7,
            "run": {
                "profile_id": "profile-51",
                "profile_fingerprint": "a" * 64,
            },
        },
    }


def _overrides() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "source_profile_id": "profile-51",
        "source_profile_fingerprint": "a" * 64,
        "routes": {},
        "evidence": [],
    }


def _install_fakes(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "build_cohort_improvement_digest", _fake_digest)
    monkeypatch.setattr(
        module,
        "build_continuous_improvement_report",
        _fake_continuous,
    )


def _fake_digest(
    audit: dict[str, object],
    *,
    experiment_overrides: dict[str, object],
) -> dict[str, object]:
    assert experiment_overrides["routes"] == {}
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "marker": audit["marker"],
        "assessment": {"top_research_priority": "route|SYMBOL"},
        "performance": {"closed_trades": 3},
    }


def _fake_continuous(
    checkpoint: dict[str, object],
    report: dict[str, object],
) -> dict[str, object]:
    assert checkpoint["audit"]["marker"] == 7
    return {
        **report,
        "continuous_improvement": True,
        "source": {
            "run_id": "run-51",
            "profile_id": "profile-51",
            "profile_fingerprint": "a" * 64,
        },
        "operational_assessment": {"status": "healthy"},
        "highest_value_next_investigation": {"route": "route|SYMBOL"},
        "hypothesis_ledger": [],
        "change_proposals": [],
    }


def _once_args(
    module: ModuleType,
    checkpoint: Path,
    output: Path,
    history: Path,
    overrides: Path,
) -> argparse.Namespace:
    return module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--out",
            str(output),
            "--history",
            str(history),
            "--decision-overrides",
            str(overrides),
            "--once",
        ]
    )


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_improvement_monitor_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
