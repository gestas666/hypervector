"""Monitor integration for source-bound SOL prospective evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"
_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_FINGERPRINT = "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
_ROUTE = "range_onset_bidirectional_v1|SOL"


def test_monitor_attaches_fresh_sol_observer_without_claiming_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rolling digest must expose pending observer maturity and source hash."""
    module = _load()
    paths = _files(tmp_path)
    _write_inputs(paths)
    _install_builders(module, monkeypatch)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(paths["checkpoint"]),
            "--out",
            str(paths["output"]),
            "--history",
            str(paths["history"]),
            "--decision-overrides",
            str(paths["overrides"]),
            "--sol-one-blocker-observer",
            str(paths["observer"]),
            "--once",
        ]
    )

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    report = json.loads(paths["output"].read_text())
    sol = report["experiment_queue"][0]
    assert sol["independent_forward_paths"] == 0
    assert sol["prospective_observation"]["independent_onsets"] == 2
    assert sol["prospective_observation"]["active_pending_lifecycles"] == 1
    assert sol["prospective_observation"]["resolved_lifecycles"] == 0
    source = report["evidence"]["sol_route_native_observer"]
    assert source["path"] == str(paths["observer"].resolve())
    assert source["sha256"]


def test_monitor_default_names_the_live_sol_observer() -> None:
    """The active v51 monitor must collect the observer without extra flags."""
    args = _load().build_parser().parse_args([])

    assert args.sol_one_blocker_observer == Path(
        "data/runtime/bidirectional_cohort/"
        "latest_v51_sol_route_native_one_blocker_shadow.json"
    )
    assert args.maximum_sol_observer_age_seconds == 360.0


def test_monitor_omits_observer_when_sol_experiment_is_retired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed experiment must not make the rolling digest unavailable."""
    module = _load()
    paths = _files(tmp_path)
    _write_inputs(paths)
    overrides = json.loads(paths["overrides"].read_text())
    overrides["routes"][_ROUTE] = {"next_experiment": "new_mechanic_version_required"}
    paths["overrides"].write_text(json.dumps(overrides))
    _install_builders(module, monkeypatch)
    monkeypatch.setattr(module, "build_cohort_improvement_digest", _retired_digest)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(paths["checkpoint"]),
            "--out",
            str(paths["output"]),
            "--history",
            str(paths["history"]),
            "--decision-overrides",
            str(paths["overrides"]),
            "--sol-one-blocker-observer",
            str(paths["observer"]),
            "--once",
        ]
    )

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    report = json.loads(paths["output"].read_text())
    assert "prospective_experiment_evidence" not in report
    assert "sol_route_native_observer" not in report["evidence"]


def _files(tmp_path: Path) -> dict[str, Path]:
    return {
        "checkpoint": tmp_path / "checkpoint.json",
        "output": tmp_path / "digest.json",
        "history": tmp_path / "history.jsonl",
        "overrides": tmp_path / "overrides.json",
        "observer": tmp_path / "observer.json",
    }


def _write_inputs(paths: dict[str, Path]) -> None:
    now = datetime.now(UTC).isoformat()
    paths["checkpoint"].write_text(json.dumps(_checkpoint(now)))
    paths["overrides"].write_text(json.dumps(_overrides()))
    paths["observer"].write_text(json.dumps(_observer(now)))


def _checkpoint(now: str) -> dict[str, object]:
    return {
        "generated_at_utc": now,
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "audit": {
            "run": {
                "run_id": "run-v51",
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
                "first_observed_at_utc": now,
            }
        },
        "configuration_generation": {
            "source_path": "config-v51.toml",
            "matches_runtime": True,
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
        "source_profile_id": _PROFILE,
        "source_profile_fingerprint": _FINGERPRINT,
        "routes": {
            _ROUTE: {"next_experiment": "collect_route_native_one_blocker_shadow"}
        },
        "evidence": [],
    }


def _observer(now: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v51_sol_route_native_one_blocker_shadow",
        "status": "candidate_lifecycle_pending",
        "observed_at_utc": now,
        "capture_start_utc": "2026-08-15T10:00:00+00:00",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "source_run_id": "run-v51",
            "source_profile_id": _PROFILE,
            "source_profile_fingerprint": _FINGERPRINT,
            "execution": {
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "SOL",
            },
        },
        "coverage": {
            "raw_exact_evaluations": 10,
            "exact_candidates": 2,
            "attempts": 1,
            "resolved_executions": 0,
            "pending_or_unresolved": 1,
        },
        "attempts": [{"status": "exit_pending", "side": "short"}],
        "executions": [],
        "portfolio_journal": {
            "schema_version": 1,
            "mode": "candidate_portfolio_compatibility_journal",
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "source_strategy_id": "range_onset_bidirectional_v1",
                "candidate_strategy_id": (
                    "sol_hourly_cross_relaxed_route_native_shadow_v1"
                ),
                "symbol": "SOL",
                "position_policy": "flat_entry_only",
                "maximum_positions": 10,
                "portfolio_pnl_claimed": False,
                "simulated_outcomes_are_non_additive": True,
            },
            "summary": {
                "attempts": 1,
                "deployable": 1,
                "deployable_resolved": 0,
                "deployable_active_pending": 1,
                "deployable_technically_unresolved": 0,
                "deployable_observed_sides": ["short"],
                "existing_symbol_position": 0,
                "portfolio_capacity": 0,
                "same_cycle_symbol_action": 0,
                "portfolio_state_unavailable": 0,
                "resolved": 0,
                "pending": 1,
            },
            "latest_attempts": [],
        },
    }


def _install_builders(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "build_cohort_improvement_digest", _digest)
    monkeypatch.setattr(module, "_external_assets_for_profile", lambda *args: None)
    monkeypatch.setattr(module, "_load_index_signals", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "build_continuous_improvement_report",
        lambda checkpoint, digest: digest,
    )
    monkeypatch.setattr(module, "append_material_report", lambda path, report: True)


def _digest(
    audit: dict[str, object], *, experiment_overrides: dict[str, object]
) -> dict[str, object]:
    run = audit["run"]
    return {
        "source": dict(run),
        "contract": {"report_only": True, "execution_authority": "none"},
        "assessment": {"top_research_priority": _ROUTE},
        "performance": {"closed_trades": 0},
        "experiment_queue": [
            {
                "route": _ROUTE,
                "next_experiment": "collect_route_native_one_blocker_shadow",
                "independent_forward_paths": 0,
                "supporting_evidence": [],
            }
        ],
    }


def _retired_digest(
    audit: dict[str, object], *, experiment_overrides: dict[str, object]
) -> dict[str, object]:
    digest = _digest(audit, experiment_overrides=experiment_overrides)
    digest["experiment_queue"][0]["next_experiment"] = "new_mechanic_version_required"
    return digest


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_improvement_monitor_prospective", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
