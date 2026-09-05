"""Durable authority-none boundary for the V58 HYPE lifecycle watcher."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

_SCRIPT = Path("scripts/hype_alignment_shadow_lifecycle_watch.py")


def _module() -> ModuleType:
    assert _SCRIPT.is_file(), "HYPE alignment shadow watcher script is missing"
    spec = spec_from_file_location("hype_alignment_shadow_watch", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_watch_once_writes_only_authority_none_status(tmp_path: Path) -> None:
    """One refresh must remain incapable of becoming a live command."""
    module = _module()
    args = _args(tmp_path)

    result = module.watch_once(args, report_builder=lambda _args: _report())

    assert args.status.is_file()
    assert result["contract"]["execution_authority"] == "none"
    assert result["watch_state"] == "awaiting_resolution"
    assert result["snapshot"] is None


def test_resolved_state_publishes_one_idempotent_snapshot(tmp_path: Path) -> None:
    """A completed virtual lifecycle must become immutable evidence once."""
    module = _module()
    args = _args(tmp_path)
    report = _report(resolved=True)

    first = module.watch_once(args, report_builder=lambda _args: report)
    second = module.watch_once(args, report_builder=lambda _args: report)

    assert first["snapshot"] == second["snapshot"]
    snapshots = list(args.snapshot_dir.glob("*.json"))
    assert len(snapshots) == 1


def test_live_shaped_report_is_rejected_before_status_write(tmp_path: Path) -> None:
    """A malformed builder cannot turn the watcher into execution authority."""
    module = _module()
    args = _args(tmp_path)
    report = _report()
    report["contract"] = {**report["contract"], "execution_authority": "live"}

    with pytest.raises(ValueError, match="report-only contract"):
        module.watch_once(args, report_builder=lambda _args: report)

    assert not args.status.exists()


def test_wrong_preregistration_hash_is_rejected_before_status(tmp_path: Path) -> None:
    """A different experiment contract cannot reuse the watcher identity."""
    module = _module()
    args = _args(tmp_path)
    args.preregistration_sha256 = "0" * 64

    with pytest.raises(ValueError, match="preregistration hash"):
        module.watch_once(args, report_builder=lambda _args: _report())

    assert not args.status.exists()


def test_changed_preregistered_ledger_prefix_is_rejected(tmp_path: Path) -> None:
    """The observer history visible at freeze time must remain immutable."""
    module = _module()
    args = _args(tmp_path)
    args.ledger.write_text('{"mutated":true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="preregistered ledger prefix changed"):
        module.watch_once(args, report_builder=lambda _args: _report())

    assert not args.status.exists()


def test_parser_has_no_live_arming_flags() -> None:
    """The CLI surface must not expose signing or execution switches."""
    module = _module()
    options = {action.dest for action in module.build_parser()._actions}

    assert "enabled" not in options
    assert "i_accept_live_risk" not in options
    assert "wallet" not in options
    assert "private_key" not in options


def test_generator_identity_covers_transitive_exact_depth_modules() -> None:
    """Frozen watcher evidence must include extracted replay dependencies."""
    paths = {str(path) for path in _module()._GENERATOR_PATHS}

    assert "src/hypervector/research/cohort_active_book_path.py" in paths
    assert "src/hypervector/research/cohort_exact_depth_attempts.py" in paths


def test_run_watcher_freezes_generators_for_process_lifetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long-lived process must reject loaded-generator drift between cycles."""
    module = _module()
    args = _args(tmp_path)
    args.config = tmp_path / "config.toml"
    args.config.write_text("mode = 'observe'\n", encoding="utf-8")
    frozen = {args.config: {"sha256": "frozen", "bytes": 17}}
    checks: list[object] = []
    monkeypatch.setattr(module, "_source_references", lambda _config: frozen)
    monkeypatch.setattr(module, "_require_unchanged", checks.append)

    result = module.run_watcher(
        args,
        report_builder=lambda _args: _report(),
        sleep_fn=lambda _seconds: None,
    )

    assert result == 0
    assert checks == [frozen, frozen]


def test_transient_transport_failure_does_not_stop_watcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One temporary public-read failure must preserve evidence and retry."""
    module = _module()
    args = _args(tmp_path)
    attempts = 0
    monkeypatch.setattr(module, "_source_references", lambda _config: {})

    def report_builder(_args: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RequestsConnectionError("temporary public read failure")
        return _report()

    result = module.run_watcher(
        args,
        report_builder=report_builder,
        sleep_fn=lambda _seconds: None,
    )

    assert result == 0
    assert attempts == 2
    assert args.status.is_file()


def _args(tmp_path: Path) -> SimpleNamespace:
    config = tmp_path / "config.toml"
    config.write_text("mode = 'observe'\n", encoding="utf-8")
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text("{}\n", encoding="utf-8")
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(json.dumps(_preregistration(ledger)), encoding="utf-8")
    return SimpleNamespace(
        preregistration=preregistration,
        preregistration_sha256=sha256(preregistration.read_bytes()).hexdigest(),
        config=config,
        ledger=ledger,
        status=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        interval_seconds=1.0,
        max_cycles=1,
        run_id="observer-v58",
    )


def _preregistration(ledger: Path) -> dict[str, object]:
    raw = ledger.read_bytes()
    return {
        "schema_version": "v58_hype_alignment_shadow_preregistration_v1",
        "strategy_id": "hype_breakout_compression_alignment_bidirectional_v2",
        "symbol": "HYPE",
        "prospective_start_ms": 0,
        "ledger_prefix": {
            "bytes": len(raw),
            "rows": 1,
            "sha256": sha256(raw).hexdigest(),
        },
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _report(*, resolved: bool = False) -> dict[str, object]:
    executions = [{"decision_time_ms": 1, "net_return_bps": 2.0}] if resolved else []
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "descriptive_exact_depth_evidence"
        if resolved
        else "awaiting_resolution",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
        },
        "summary": {"resolved": len(executions)},
        "latest_attempts": [],
        "latest_executions": executions,
    }
