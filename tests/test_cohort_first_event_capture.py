"""Contracts for immutable first-event evidence capture."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


MODULE = Path("src/hypervector/research/cohort_first_event_capture.py")
SCRIPT = Path("scripts/cohort_first_event_capture.py")


def test_first_event_capture_sources_exist() -> None:
    """The trigger must have an isolated report-only capture boundary."""
    assert MODULE.is_file()
    assert SCRIPT.is_file()


def test_quiet_checkpoint_publishes_waiting_status_without_commands(
    tmp_path: Path,
) -> None:
    """A zero-delta prefix must not manufacture immutable event artifacts."""
    module = _load_script()
    args = _args(tmp_path, eligible=0, intents=0, actions=0)
    commands: list[tuple[str, ...]] = []

    status = module.capture_once(args, command_runner=commands.append)

    assert status["state"] == "awaiting_first_event"
    assert commands == []
    assert json.loads(args.status.read_text()) == status
    assert not list(args.out_dir.rglob("*.json"))


def test_first_accounted_event_publishes_audit_delta_and_manifest(
    tmp_path: Path,
) -> None:
    """One eligible routed outcome must freeze the promised evidence bundle."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    commands: list[tuple[str, ...]] = []

    status = module.capture_once(
        args,
        command_runner=_fake_runner(commands, _identity()),
    )

    assert status["state"] == "captured"
    assert len(commands) == 2
    assert all("--enabled" not in command for command in commands)
    assert all("--i-accept-live-risk" not in command for command in commands)
    assert commands[0][-2:] == ("--history-scope", "current-run")
    manifest = json.loads(Path(status["manifest_path"]).read_text())
    assert manifest["contract"]["execution_authority"] == "none"
    assert manifest["trigger"]["counter_deltas"]["eligible_evaluations"] == 1
    assert manifest["trigger"]["counter_deltas"]["actions"] == 1
    assert manifest["source_evidence"]["after_audit"]["sha256"]
    assert manifest["source_evidence"]["delta"]["sha256"]


def test_completed_capture_is_idempotent_across_restart(tmp_path: Path) -> None:
    """A durable manifest must prevent duplicate first-event artifacts."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    first_commands: list[tuple[str, ...]] = []
    module.capture_once(
        args,
        command_runner=_fake_runner(first_commands, _identity()),
    )
    second_commands: list[tuple[str, ...]] = []

    status = module.capture_once(args, command_runner=second_commands.append)

    assert status["state"] == "already_captured"
    assert second_commands == []


def test_resolution_mode_waits_for_close_then_captures_exactly_once(
    tmp_path: Path,
) -> None:
    """An action must not end the watcher before its first lifecycle resolves."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    args.terminal_state = "resolved_lifecycle"
    commands: list[tuple[str, ...]] = []

    waiting = module.capture_once(args, command_runner=commands.append)

    assert waiting["state"] == "awaiting_resolved_lifecycle"
    assert commands == []
    checkpoint = json.loads(args.checkpoint.read_text())
    checkpoint["audit"]["execution"]["closed_trades"] = 1
    args.checkpoint.write_text(json.dumps(checkpoint))

    captured = module.capture_once(
        args,
        command_runner=_fake_runner(commands, _identity()),
    )

    assert captured["state"] == "captured"
    manifest = json.loads(Path(captured["manifest_path"]).read_text())
    assert manifest["capture_stage"] == "resolved_lifecycle"
    assert manifest["trigger"]["counter_deltas"]["closed_trades"] == 1
    assert "resolved_lifecycle" in captured["manifest_path"]


def test_foreign_profile_override_fails_before_capture(tmp_path: Path) -> None:
    """A frozen hypothesis for another profile cannot capture current ledgers."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    overrides = json.loads(args.decision_overrides.read_text())
    overrides["source_profile_fingerprint"] = "b" * 64
    args.decision_overrides.write_text(json.dumps(overrides))

    with pytest.raises(ValueError, match="profile fingerprint"):
        module.capture_once(args, command_runner=lambda command: None)


def test_quiet_watcher_rejects_missing_baseline_before_event(tmp_path: Path) -> None:
    """Capture readiness cannot wait until an event to discover lost evidence."""
    module = _load_script()
    args = _args(tmp_path, eligible=0, intents=0, actions=0)
    overrides = json.loads(args.decision_overrides.read_text())
    Path(overrides["active_hypotheses"][0]["evidence_baseline"]).unlink()

    with pytest.raises(FileNotFoundError, match="baseline audit is missing"):
        module.capture_once(args, command_runner=lambda command: None)


def test_capture_command_failure_leaves_no_success_manifest(tmp_path: Path) -> None:
    """A failed evidence command cannot produce success-shaped capture state."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)

    def fail(_command: tuple[str, ...]) -> None:
        raise RuntimeError("audit command failed")

    with pytest.raises(RuntimeError, match="audit command failed"):
        module.capture_once(args, command_runner=fail)

    assert not list(args.out_dir.rglob("manifest.json"))


def test_capture_rejects_decision_override_change_during_audit(
    tmp_path: Path,
) -> None:
    """One capture cannot mix trigger and post-audit research-contract bytes."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    commands: list[tuple[str, ...]] = []
    base_runner = _fake_runner(commands, _identity())

    def mutate_after_audit(command: tuple[str, ...]) -> None:
        base_runner(command)
        if command[1].endswith("multi_asset_bidirectional_live_audit.py"):
            payload = json.loads(args.decision_overrides.read_text())
            payload["active_hypotheses"][0]["decision_source"] = "changed.json"
            args.decision_overrides.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="decision overrides changed"):
        module.capture_once(args, command_runner=mutate_after_audit)

    assert not list(args.out_dir.rglob("manifest.json"))
    with pytest.raises(ValueError, match="capture source snapshot mismatch"):
        module.capture_once(args, command_runner=base_runner)


def test_capture_rejects_baseline_change_during_audit(tmp_path: Path) -> None:
    """One capture cannot compare against baseline bytes changed mid-audit."""
    module = _load_script()
    args = _args(tmp_path, eligible=1, intents=1, actions=1)
    overrides = json.loads(args.decision_overrides.read_text())
    baseline = Path(overrides["active_hypotheses"][0]["evidence_baseline"])
    commands: list[tuple[str, ...]] = []
    base_runner = _fake_runner(commands, _identity())

    def mutate_after_audit(command: tuple[str, ...]) -> None:
        base_runner(command)
        if command[1].endswith("multi_asset_bidirectional_live_audit.py"):
            payload = json.loads(baseline.read_text())
            payload["generated_at_utc"] = "2026-08-17T20:00:00Z"
            baseline.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="baseline audit changed"):
        module.capture_once(args, command_runner=mutate_after_audit)

    assert not list(args.out_dir.rglob("manifest.json"))


def test_main_holds_singleton_status_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only one long-running watcher may own a mutable status destination."""
    module = _load_script()
    status = tmp_path / "status.json"
    events: list[object] = []

    @contextmanager
    def lock(path: Path) -> Iterator[Path]:
        events.append(("lock", path))
        yield path.with_name(f"{path.name}.writer.lock")
        events.append("unlock")

    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", lock)
    monkeypatch.setattr(
        module,
        "run_watcher",
        lambda args: events.append("run") or 0,
    )
    argv = [
        "--decision-overrides",
        str(tmp_path / "overrides.json"),
        "--out-dir",
        str(tmp_path / "out"),
        "--status",
        str(status),
        "--hypothesis-id",
        "first-event-v1",
        "--once",
    ]

    assert module.main(argv) == 0
    assert events == [("lock", status), "run", "unlock"]


def test_main_converts_keyboard_interrupt_to_clean_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator shutdown must release the lock without a Python traceback."""
    module = _load_script()

    @contextmanager
    def lock(path: Path) -> Iterator[Path]:
        yield path.with_name(f"{path.name}.writer.lock")

    def interrupt(_args: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", lock)
    monkeypatch.setattr(module, "run_watcher", interrupt)

    assert module.main(_minimal_argv(tmp_path)) == 130


def _minimal_argv(tmp_path: Path) -> list[str]:
    return [
        "--decision-overrides",
        str(tmp_path / "overrides.json"),
        "--out-dir",
        str(tmp_path / "out"),
        "--status",
        str(tmp_path / "status.json"),
        "--hypothesis-id",
        "first-event-v1",
        "--once",
    ]


def _load_script() -> ModuleType:
    spec = spec_from_file_location("cohort_first_event_capture_command", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(
    tmp_path: Path,
    *,
    eligible: int,
    intents: int,
    actions: int,
) -> argparse.Namespace:
    identity = _identity()
    checkpoint = tmp_path / "checkpoint.json"
    overrides = tmp_path / "overrides.json"
    baseline = tmp_path / "baseline.json"
    checkpoint.write_text(json.dumps(_checkpoint(identity, eligible, intents, actions)))
    baseline.write_text(json.dumps(_audit_report(identity)))
    overrides.write_text(json.dumps(_overrides(identity, baseline)))
    return argparse.Namespace(
        checkpoint=checkpoint,
        decision_overrides=overrides,
        ledger_root=tmp_path / "ledgers",
        out_dir=tmp_path / "captures",
        status=tmp_path / "latest.json",
        hypothesis_id="first-event-v1",
        interval_seconds=5.0,
        once=True,
        max_cycles=0,
    )


def _identity() -> dict[str, str]:
    return {
        "run_id": "run-1",
        "profile_id": "profile-1",
        "profile_fingerprint": "a" * 64,
    }


def _checkpoint(
    identity: dict[str, str], eligible: int, intents: int, actions: int
) -> dict[str, object]:
    return {
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": identity["profile_fingerprint"],
        },
        "audit": {
            "experiment_contract": {
                "report_only": True,
                "execution_authority": "none",
                "runtime_strategy_changed": False,
            },
            "run": {
                **identity,
                "row_count": 100,
                "last_observed_at_utc": "2026-08-16T00:00:00Z",
            },
            "routing": {
                "strategy_intents": intents,
                "actions": actions,
                "withheld": 0,
                "entry_age_diagnostics": {"eligible_evaluations": eligible},
            },
            "execution": {
                "fills": 0,
                "closed_trades": 0,
                "by_asset": {"BTC": {"open_lifecycles": 0}},
            },
        },
    }


def _overrides(identity: dict[str, str], baseline: Path) -> dict[str, object]:
    return {
        "source_profile_id": identity["profile_id"],
        "source_profile_fingerprint": identity["profile_fingerprint"],
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "active_hypotheses": [
            {
                "hypothesis_id": "first-event-v1",
                "status": "being_tested",
                "execution_effect": "report_only",
                "decision_source": "decision.json",
                "evidence_baseline": str(baseline),
                "baseline_identity": identity,
                "baseline_counters": _counters(),
            }
        ],
    }


def _counters() -> dict[str, int]:
    return {
        "eligible_evaluations": 0,
        "strategy_intents": 0,
        "actions": 0,
        "withheld": 0,
        "fills": 0,
        "open_lifecycles": 0,
        "closed_trades": 0,
    }


def _audit_report(identity: dict[str, str]) -> dict[str, object]:
    return {
        "experiment_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "run": {
            **identity,
            "row_count": 100,
            "last_observed_at_utc": "2026-08-16T00:00:00Z",
        },
    }


def _delta_report(identity: dict[str, str]) -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "identity": identity,
    }


def _fake_runner(
    commands: list[tuple[str, ...]], identity: dict[str, str]
) -> Callable[[tuple[str, ...]], None]:
    def run(command: tuple[str, ...]) -> None:
        commands.append(command)
        output = Path(command[command.index("--out") + 1])
        payload = (
            _audit_report(identity)
            if command[1].endswith("multi_asset_bidirectional_live_audit.py")
            else _delta_report(identity)
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload))

    return run
