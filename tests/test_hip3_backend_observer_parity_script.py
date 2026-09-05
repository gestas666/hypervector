"""Immutable CLI tests for active-backend versus observer parity."""

from __future__ import annotations

from argparse import Namespace
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

from test_hip3_backend_observer_parity import _cohort_row, _observer_row

_SCRIPT = Path("scripts/hip3_backend_observer_parity.py")


def test_report_binds_checkpoint_ledger_prefix_and_both_observers(
    tmp_path: Path,
) -> None:
    """Publication must preserve exact live-run and source-prefix evidence."""
    module, args, output, cohort_raw = _matching_case(tmp_path)

    report = module.run_report(args)
    module.publish_report(output, report)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert (
        persisted["technical_assessment"]["backend_observer_decision_parity_resolved"]
        is True
    )
    assert (
        persisted["input_evidence"]["cohort_prefix"]["sha256"]
        == sha256(cohort_raw).hexdigest()
    )
    assert set(persisted["input_evidence"]["observer_prefixes"]) == {
        "xyz:SP500",
        "xyz:SPCX",
    }
    assert persisted["generator_identity"]["files"]
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(output, report)


def test_changed_nonroute_cohort_prefix_fails_before_publication(
    tmp_path: Path,
) -> None:
    """Checkpoint hashing must protect even rows outside the selected route."""
    module, args = _changed_prefix_case(tmp_path)

    with pytest.raises(
        RuntimeError,
        match="cohort ledger prefix differs from checkpoint evidence",
    ):
        module.run_report(args)


def test_report_verifies_compatible_execution_suffix_evidence(
    tmp_path: Path,
) -> None:
    """A bounded checkpoint hash must bind its exact compatible-ledger suffix."""
    module, args, output, suffix_raw = _compatible_suffix_case(tmp_path)

    report = module.run_report(args)
    module.publish_report(output, report)

    evidence = report["input_evidence"]["cohort_prefix"]
    assert evidence["snapshot_scope"] == "compatible_execution_history"
    assert evidence["source_start_offset"] > 0
    assert evidence["bytes"] == len(suffix_raw)
    assert evidence["sha256"] == sha256(suffix_raw).hexdigest()


def _matching_case(tmp_path: Path) -> tuple[ModuleType, Namespace, Path, bytes]:
    module = _module()
    cohort_path = tmp_path / "decisions.jsonl"
    observers = {
        "xyz:SP500": tmp_path / "sp500.jsonl",
        "xyz:SPCX": tmp_path / "spcx.jsonl",
    }
    cohort_raw = _jsonl(
        tuple(
            _cohort_row(900_000, symbol, imbalance=imbalance)
            for symbol, imbalance in (("xyz:SP500", 0.25), ("xyz:SPCX", -0.25))
        )
    )
    cohort_path.write_bytes(cohort_raw)
    for symbol, path in observers.items():
        imbalance = 0.25 if symbol == "xyz:SP500" else -0.25
        path.write_bytes(_jsonl((_observer_row(900_000, symbol, imbalance=imbalance),)))
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps(_checkpoint(cohort_path, cohort_raw)))
    output = tmp_path / "report.json"
    args = _args(module, checkpoint, cohort_path, observers, output)
    return module, args, output, cohort_raw


def _changed_prefix_case(tmp_path: Path) -> tuple[ModuleType, Namespace]:
    module = _module()
    heartbeat = {"event_type": "heartbeat", "value": 1}
    route = _cohort_row(900_000, "xyz:SP500", imbalance=0.25)
    cohort_raw = _jsonl((heartbeat, route))
    cohort_path = tmp_path / "decisions.jsonl"
    cohort_path.write_bytes(cohort_raw)
    observer_path = tmp_path / "sp500.jsonl"
    observer_path.write_bytes(
        _jsonl((_observer_row(900_000, "xyz:SP500", imbalance=0.25),))
    )
    checkpoint = tmp_path / "checkpoint.json"
    payload = _checkpoint(cohort_path, cohort_raw)
    generation = payload["configuration_generation"]
    assert isinstance(generation, dict)
    generation["current_provider_execution_scopes"] = {"index-v3": ["xyz:SP500"]}
    run = payload["audit"]["run"]
    run["executable_provider_symbols"] = ["index-v3|xyz:SP500"]
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    cohort_path.write_bytes(_jsonl(({**heartbeat, "value": 2}, route)))
    args = _args(
        module,
        checkpoint,
        cohort_path,
        {"xyz:SP500": observer_path},
        tmp_path / "report.json",
    )
    return module, args


def _compatible_suffix_case(
    tmp_path: Path,
) -> tuple[ModuleType, Namespace, Path, bytes]:
    module, args, output, suffix_raw = _matching_case(tmp_path)
    cohort_path = Path(args.cohort_ledger)
    old_raw = _jsonl((_cohort_row(800_000, "xyz:SP500", imbalance=-0.5),))
    cohort_path.write_bytes(old_raw + suffix_raw)
    checkpoint_path = Path(args.checkpoint)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    evidence = checkpoint["evidence"]["cohort"]
    evidence.update(
        {
            "bytes": len(suffix_raw),
            "sha256": sha256(suffix_raw).hexdigest(),
            "snapshot_scope": "compatible_execution_history",
            "source_start_offset": len(old_raw),
            "stable_bytes": len(old_raw) + len(suffix_raw),
        }
    )
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    return module, args, output, suffix_raw


def _args(
    module: ModuleType,
    checkpoint: Path,
    cohort: Path,
    observers: dict[str, Path],
    output: Path,
) -> Namespace:
    observer_args = [
        item
        for pair in observers.items()
        for item in ("--observer", f"{pair[0]}={pair[1]}")
    ]
    return module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--cohort-ledger",
            str(cohort),
            *observer_args,
            "--provider-id",
            "index-v3",
            "--output",
            str(output),
        ]
    )


def _checkpoint(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-14T00:00:00+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "configuration_generation": {
            "state": "current_runtime_configuration",
            "matches_runtime": True,
            "current_profile_fingerprint": "fingerprint",
            "runtime_profile_fingerprint": "fingerprint",
            "current_provider_execution_scopes": {
                "index-v3": ["xyz:SP500", "xyz:SPCX"]
            },
        },
        "audit": {
            "run": {
                "run_id": "live-run",
                "profile_id": "v51",
                "profile_fingerprint": "fingerprint",
                "first_observed_at_utc": "1970-01-01T00:00:00.001+00:00",
                "symbols": ["xyz:SP500", "xyz:SPCX"],
                "executable_provider_symbols": [
                    "index-v3|xyz:SP500",
                    "index-v3|xyz:SPCX",
                ],
            }
        },
        "evidence": {
            "cohort": {
                "path": str(path),
                "bytes": len(raw),
                "stable_bytes": len(raw),
                "sha256": sha256(raw).hexdigest(),
            }
        },
    }


def _jsonl(rows: tuple[dict[str, object], ...]) -> bytes:
    return b"".join((json.dumps(row) + "\n").encode() for row in rows)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("HIP-3 backend-observer parity script is missing")
    spec = spec_from_file_location("hip3_backend_observer_parity_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load backend-observer parity script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
