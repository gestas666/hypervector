"""CLI orchestration for the report-only V58 BRENTOIL lifecycle watcher."""

from __future__ import annotations

import argparse
from importlib import util
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence


def test_open_cycle_writes_only_atomic_status(tmp_path: Path) -> None:
    """An unresolved lifecycle must not create a success-shaped final artifact."""
    module = _module()
    args = _args(tmp_path)
    args.preregistration_sha256 = _write_preregistration(args.preregistration)
    writes: list[tuple[Path, dict[str, object]]] = []

    result = module.run_watcher(
        args,
        cycle_loader=lambda *_: _report("open_protected"),
        atomic_writer=lambda path, payload: writes.append((path, payload)),
        immutable_writer=lambda *_: pytest.fail("open lifecycle published a final"),
        generator_paths=lambda: (args.config,),
        sleep_fn=lambda _: None,
    )

    assert result == 0
    assert [path for path, _ in writes] == [args.status]
    assert writes[0][1]["state"] == "open_protected"
    assert not args.final.exists()


def test_resolved_cycle_publishes_one_immutable_final_then_status(
    tmp_path: Path,
) -> None:
    """A resolved lifecycle must publish exact final bytes before mutable status."""
    module = _module()
    args = _args(tmp_path)
    args.preregistration_sha256 = _write_preregistration(args.preregistration)
    events: list[tuple[str, Path]] = []

    result = module.run_watcher(
        args,
        cycle_loader=lambda *_: _report("resolved"),
        atomic_writer=lambda path, _: events.append(("status", path)),
        immutable_writer=lambda path, _: events.append(("final", path)),
        generator_paths=lambda: (args.config,),
        sleep_fn=lambda _: None,
    )

    assert result == 0
    assert events == [("final", args.final), ("status", args.status)]


def test_existing_preregistration_requires_explicit_hash(tmp_path: Path) -> None:
    """Restart must not silently trust a replaceable preregistration path."""
    module = _module()
    args = _args(tmp_path)
    _write_preregistration(args.preregistration)
    args.preregistration_sha256 = None

    with pytest.raises(ValueError, match="requires --preregistration-sha256"):
        module.run_watcher(
            args,
            cycle_loader=lambda *_: _report("open_protected"),
            generator_paths=lambda: (args.config,),
            sleep_fn=lambda _: None,
        )


def _module() -> object:
    """Load the watcher only after proving its script exists."""
    path = Path("scripts/v58_brentoil_live_lifecycle_watch.py")
    spec = util.spec_from_file_location("v58_brentoil_watch", path)
    assert spec is not None and spec.loader is not None, "BRENTOIL watcher is missing"
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path) -> argparse.Namespace:
    """Return a one-cycle report-only watcher namespace."""
    config = tmp_path / "v58.toml"
    config.write_text("profile = 'v58'\n", encoding="utf-8")
    preregistration = tmp_path / "preregistration.json"
    return argparse.Namespace(
        checkpoint=tmp_path / "checkpoint.json",
        venue=tmp_path / "venue.json",
        ledger=tmp_path / "xyz:brentoil.jsonl",
        config=config,
        prestart_manifest=tmp_path / "manifest.json",
        preregistration=preregistration,
        preregistration_sha256="a" * 64,
        status=tmp_path / "status.json",
        final=tmp_path / "final.json",
        interval_seconds=1.0,
        max_cycles=1,
    )


def _write_preregistration(path: Path) -> str:
    """Write one exact fixture and return its SHA-256 identity."""
    path.write_text('{"contract":{"execution_authority":"none"}}\n', encoding="utf-8")
    return str(file_evidence(path)["sha256"])


def _report(state: str) -> dict[str, object]:
    """Return a compact reconciled cycle payload."""
    return {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_reconciliation_v1",
        "state": state,
        "identity": {"lifecycle_id": "xyz:BRENTOIL:520642502465"},
        "summary": {
            "open": int(state != "resolved"),
            "resolved": int(state == "resolved"),
        },
        "actual_live_lifecycle": {},
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "actual_orders_or_fills_claimed": True,
            "portfolio_pnl_claimed": False,
        },
    }
