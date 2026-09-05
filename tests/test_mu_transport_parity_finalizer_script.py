"""Script-level tests for the report-only MU window finalizer."""

from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts/mu_transport_parity_finalizer.py"


def _load_script() -> ModuleType:
    spec = spec_from_file_location("mu_transport_parity_finalizer_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def _evidence(path: Path) -> dict[str, object]:
    return {
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def _source_contract(tmp_path: Path, root: Path) -> Path:
    generator = root / "scripts/generator.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("frozen\n")
    artifact = tmp_path / "baseline.json"
    _write_json(
        artifact, {"generator_identity": {"scripts/generator.py": _evidence(generator)}}
    )
    source = tmp_path / "source.json"
    _write_json(
        source,
        {
            "refreshed_evidence": {
                key: {"path": "baseline.json", **_evidence(artifact)}
                for key in ("venue_path", "candle_source", "strategy_signal_source")
            }
        },
    )
    return source


def _prereg(tmp_path: Path, root: Path, source: Path) -> Path:
    script = root / "scripts/hip3_shadow_observer_decision_parity.py"
    module = root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py"
    script.write_text("script\n")
    module.parent.mkdir(parents=True)
    module.write_text("module\n")
    prereg = tmp_path / "prereg.json"
    _write_json(prereg, _prereg_payload(source, script, module))
    return prereg


def _prereg_payload(source: Path, script: Path, module: Path) -> dict[str, object]:
    return {
        "schema_version": "v52_mu_transport_parity_forward_window_v1",
        "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
        "scope": {
            "symbol": "xyz:MU",
            "provider_id": "provider",
            "profile_id": "profile",
            "timeframe": "15m",
            "first_decision_ms": 900_000,
            "last_decision_ms": 1_800_000,
            "end_exclusive_ms": 2_700_000,
            "expected_decisions": 2,
        },
        "frozen_sources": {
            "source_journal": {
                "path": "source.json",
                "sha256": _evidence(source)["sha256"],
            },
            "bounded_report_module_sha256": _evidence(module)["sha256"],
            "bounded_report_script_sha256": _evidence(script)["sha256"],
        },
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "promotion_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "no_window_shrinkage": True,
            "no_replacement_window_after_failure": True,
            "no_parameter_retuning_during_window": True,
        },
    }


def _observer_row(decision_time_ms: int) -> dict[str, object]:
    return {
        "event_type": "mu_hip3_breakout_shadow_decision",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "intents": [],
        "decision": {
            "symbol": "xyz:MU",
            "provider_id": "provider",
            "profile_id": "profile",
            "decision_time_ms": decision_time_ms,
            "eligible": False,
            "side": None,
            "prospective": True,
            "execution_authority": "none",
            "pressure_source": "hyperliquid_mainnet_l2_rest",
            "pressure_state_history_complete": True,
            "pressure_fresh": True,
            "pressure_scan_complete": True,
        },
    }


def _args(
    tmp_path: Path, root: Path, prereg: Path, observer: Path
) -> argparse.Namespace:
    diagnostic = tmp_path / "diagnostic.json"
    _write_json(diagnostic, {"execution_authority": "none"})
    return argparse.Namespace(
        prereg=prereg,
        observer_journal=observer,
        development_diagnostic=diagnostic,
        data_root=tmp_path / "data",
        out_dir=tmp_path / "out",
        status=tmp_path / "status.json",
        root=root,
        interval_seconds=1.0,
        max_cycles=0,
        once=True,
        source_hash_correction=None,
    )


def test_before_window_waits_without_running_evidence_chain(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_observer_row(900_000)) + "\n")
    args = _args(tmp_path, root, prereg, observer)
    commands: list[tuple[str, ...]] = []

    result = _load_script().finalize_once(
        args, now_ms=2_699_999, command_runner=commands.append
    )

    assert result["state"] == "collecting"
    assert result["observed_decisions"] == 1
    assert result["past_due_missing_decisions"] == [1_800_000]
    assert result["technical_alert"] == "missing_past_decision"
    assert commands == []
    assert not list(args.out_dir.rglob("manifest.json"))


def test_future_missing_decision_is_not_reported_as_stale(tmp_path: Path) -> None:
    """Independent health reporting must not classify a future row as lost."""
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_observer_row(900_000)) + "\n")
    args = _args(tmp_path, root, prereg, observer)

    result = _load_script().finalize_once(
        args,
        now_ms=1_799_999,
        command_runner=lambda _command: None,
    )

    assert result["state"] == "collecting"
    assert result["past_due_missing_decisions"] == []
    assert result["technical_alert"] is None


def test_past_unresolved_decision_is_reported_as_technical_alert(
    tmp_path: Path,
) -> None:
    """A present row with unusable pressure must not look healthy indefinitely."""
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    rows = [_observer_row(900_000), _observer_row(1_800_000)]
    rows[1]["decision"]["pressure_fresh"] = False  # type: ignore[index]
    observer.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = _args(tmp_path, root, prereg, observer)

    result = _load_script().finalize_once(
        args,
        now_ms=2_699_999,
        command_runner=lambda _command: None,
    )

    assert result["state"] == "collecting"
    assert result["past_due_missing_decisions"] == []
    assert result["past_due_unresolved_decisions"] == [1_800_000]
    assert result["technical_alert"] == "unresolved_past_decision"


def test_closed_window_publishes_missing_decision_failure(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_observer_row(900_000)) + "\n")
    args = _args(tmp_path, root, prereg, observer)
    commands: list[tuple[str, ...]] = []

    result = _load_script().finalize_once(
        args, now_ms=2_700_000, command_runner=commands.append
    )

    manifest_path = Path(str(result["manifest_path"]))
    manifest = json.loads(manifest_path.read_text())
    assert result["state"] == "finalized_fail"
    assert manifest["verdict"] == "FAIL"
    assert manifest["failure_reasons"] == ["missing_observer_decisions"]
    assert manifest["observer_progress"]["missing_decisions"] == [1_800_000]
    assert commands == []


def test_complete_window_runs_frozen_chain_and_publishes_pass(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    rows = [_observer_row(900_000), _observer_row(1_800_000)]
    rows[1]["decision"]["eligible"] = True
    rows[1]["decision"]["side"] = "short"
    observer.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = _args(tmp_path, root, prereg, observer)
    correction = tmp_path / "correction.json"
    _write_json(correction, {"report_only": True})
    args.source_hash_correction = correction
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...]) -> None:
        commands.append(command)
        _write_chain_output(command, expected_decisions=2)

    result = _load_script().finalize_once(args, now_ms=2_700_000, command_runner=run)

    manifest = json.loads(Path(str(result["manifest_path"])).read_text())
    assert result["state"] == "finalized_pass"
    assert manifest["verdict"] == "PASS"
    assert manifest["failure_reasons"] == []
    assert manifest["source_evidence"]["source_hash_correction"] == {
        "path": str(correction.resolve()),
        **_evidence(correction),
    }
    assert set(manifest["chain_evidence"]) == {
        "path_audit",
        "candle_parity",
        "signal_parity",
        "decision_parity",
    }
    assert [Path(command[1]).name for command in commands] == [
        "hip3_prospective_path_audit.py",
        "hip3_prospective_candle_parity.py",
        "hip3_prospective_signal_parity.py",
        "hip3_shadow_observer_decision_parity.py",
    ]
    assert commands[-1][commands[-1].index("--start-ms") + 1] == "900000"
    assert commands[-1][commands[-1].index("--end-ms") + 1] == "1800000"

    commands.clear()
    repeated = _load_script().finalize_once(
        args, now_ms=2_700_001, command_runner=commands.append
    )
    assert repeated["state"] == "already_finalized_pass"
    assert commands == []


def test_watcher_polls_to_boundary_and_stops_after_publication(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(
        "\n".join(json.dumps(_observer_row(value)) for value in (900_000, 1_800_000))
        + "\n"
    )
    args = _args(tmp_path, root, prereg, observer)
    args.once = False
    clocks = iter((2_699_999, 2_700_000))
    sleeps: list[float] = []

    def run(command: tuple[str, ...]) -> None:
        _write_chain_output(command, expected_decisions=2)

    result = _load_script().run_watcher(
        args,
        command_runner=run,
        clock_ms=lambda: next(clocks),
        sleep_fn=sleeps.append,
    )

    assert result == 0
    assert sleeps == [1.0]
    assert json.loads(args.status.read_text())["state"] == "finalized_pass"


def test_watcher_rejects_preregistration_change_between_cycles(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_observer_row(900_000)) + "\n")
    args = _args(tmp_path, root, prereg, observer)
    args.once = False
    clocks = iter((1_799_999, 2_700_000))

    def mutate_preregistration(_seconds: float) -> None:
        payload = json.loads(prereg.read_text())
        payload["post_start_mutation"] = True
        _write_json(prereg, payload)

    with pytest.raises(RuntimeError, match="preregistration changed"):
        _load_script().run_watcher(
            args,
            command_runner=lambda _command: None,
            clock_ms=lambda: next(clocks),
            sleep_fn=mutate_preregistration,
        )

    assert not list(args.out_dir.rglob("manifest.json"))


def test_chain_error_publishes_one_immutable_failure(tmp_path: Path) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(
        "\n".join(json.dumps(_observer_row(value)) for value in (900_000, 1_800_000))
        + "\n"
    )
    args = _args(tmp_path, root, prereg, observer)
    calls = 0

    def fail(command: tuple[str, ...]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            _write_chain_output(command, expected_decisions=2)
            return
        raise RuntimeError("bounded evidence command failed")

    result = _load_script().finalize_once(args, now_ms=2_700_000, command_runner=fail)

    manifest = json.loads(Path(str(result["manifest_path"])).read_text())
    assert result["state"] == "finalized_fail"
    assert manifest["verdict"] == "FAIL"
    assert manifest["failure_reasons"] == ["evidence_chain_failed"]
    assert manifest["failure_detail"] == "bounded evidence command failed"
    assert calls == 2


def test_generator_change_is_held_then_published_as_fixed_window_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = _source_contract(tmp_path, root)
    prereg = _prereg(tmp_path, root, source)
    observer = tmp_path / "observer.jsonl"
    observer.write_text(json.dumps(_observer_row(900_000)) + "\n")
    args = _args(tmp_path, root, prereg, observer)
    (root / "scripts/generator.py").write_text("changed\n")
    commands: list[tuple[str, ...]] = []
    script = _load_script()

    collecting = script.finalize_once(
        args, now_ms=2_699_999, command_runner=commands.append
    )
    final = script.finalize_once(args, now_ms=2_700_000, command_runner=commands.append)

    manifest = json.loads(Path(str(final["manifest_path"])).read_text())
    assert collecting["state"] == "collecting_source_failure"
    assert final["state"] == "finalized_fail"
    assert manifest["failure_reasons"] == ["frozen_generator_changed"]
    assert commands == []


def _write_chain_output(command: tuple[str, ...], *, expected_decisions: int) -> None:
    output = Path(command[command.index("--output") + 1])
    script = Path(command[1]).name
    payload = _chain_payload(script, expected_decisions)
    _write_json(output, payload)


def _chain_payload(script: str, expected_decisions: int) -> dict[str, object]:
    contract = {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    schemas = {
        "hip3_prospective_path_audit.py": "hip3_prospective_path_audit_v1",
        "hip3_prospective_candle_parity.py": "hip3_prospective_candle_parity_v1",
        "hip3_prospective_signal_parity.py": "hip3_prospective_signal_parity_v1",
    }
    if script in schemas:
        return {
            "schema_version": schemas[script],
            "contract": contract,
            "technical_assessment": {"prospective_signal_source_parity_resolved": True},
        }
    return {
        "schema_version": "hip3_shadow_observer_decision_parity_v2",
        "contract": contract,
        "scope": {
            "symbol": "xyz:MU",
            "provider_id": "provider",
            "profile_id": "profile",
            "timeframe": "15m",
        },
        "coverage": {
            "comparison_start_ms": 900_000,
            "comparison_end_ms": 1_800_000,
            "comparison_window_policy": "explicit_requested_bounds",
        },
        "technical_assessment": {
            "comparison_decisions": expected_decisions,
            "missing_observer_decisions": 0,
            "entry_decision_mismatches": 0,
            "non_vacuous_entry_comparison": True,
            "observer_archive_pressure_decision_parity_resolved": True,
        },
    }
