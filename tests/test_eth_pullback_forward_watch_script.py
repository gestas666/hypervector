"""Durable authority-none boundary for the V58 ETH lifecycle watcher."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts/eth_pullback_forward_watch.py"


def test_pending_status_is_report_only(tmp_path: Path) -> None:
    """One refresh cannot construct execution authority or claim a close."""
    module = _module()
    args = _args(tmp_path)

    status = module.watch_once(args, report_builder=lambda _args: _report())

    assert status["contract"]["execution_authority"] == "none"
    assert status["watch_state"] == "awaiting_resolution"
    assert status["snapshot"] is None


def test_resolved_report_publishes_one_snapshot(tmp_path: Path) -> None:
    """An unchanged resolved lifecycle must be idempotently immutable."""
    module = _module()
    args = _args(tmp_path)

    first = module.watch_once(args, report_builder=lambda _args: _report(True))
    second = module.watch_once(args, report_builder=lambda _args: _report(True))

    assert first["snapshot"] == second["snapshot"]
    assert len(list(args.snapshot_dir.glob("*.json"))) == 1


def test_wrong_preregistration_hash_is_rejected(tmp_path: Path) -> None:
    """A different ETH experiment cannot reuse this watcher identity."""
    module = _module()
    args = _args(tmp_path)
    args.preregistration_sha256 = "0" * 64

    with pytest.raises(ValueError, match="preregistration hash"):
        module.watch_once(args, report_builder=lambda _args: _report())

    assert not args.status.exists()


def test_parser_has_no_execution_or_secret_flags() -> None:
    """The watcher CLI must remain structurally execution-incapable."""
    options = {action.dest for action in _module().build_parser()._actions}

    assert "enabled" not in options
    assert "i_accept_live_risk" not in options
    assert "wallet" not in options
    assert "private_key" not in options


def test_generator_identity_covers_transitive_exact_depth_modules() -> None:
    """Frozen watcher evidence must include extracted replay dependencies."""
    paths = {str(path) for path in _module()._GENERATOR_PATHS}

    assert "src/hypervector/research/cohort_active_book_path.py" in paths
    assert "src/hypervector/research/cohort_exact_depth_attempts.py" in paths


def test_transient_transport_failure_does_not_stop_watcher(tmp_path: Path) -> None:
    """One temporary public-read failure preserves the last status and retries."""
    module = _module()
    args = _args(tmp_path)
    attempts = 0

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


def _module() -> ModuleType:
    assert _SCRIPT.is_file(), "ETH pullback forward watcher is missing"
    scripts = str(_SCRIPT.parent)
    sys.path.insert(0, scripts)
    try:
        spec = spec_from_file_location("eth_pullback_forward_watch_script", _SCRIPT)
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts)


def _args(tmp_path: Path) -> SimpleNamespace:
    config = tmp_path / "config.toml"
    config.write_text("profile='fixture'\n", encoding="utf-8")
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text("{}\n", encoding="utf-8")
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(
        json.dumps(_preregistration(config, ledger)), encoding="utf-8"
    )
    return SimpleNamespace(
        preregistration=preregistration,
        preregistration_sha256=sha256(preregistration.read_bytes()).hexdigest(),
        config=config,
        ledger=ledger,
        observer_ledger_root=tmp_path,
        run_id="observer-run",
        status=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        taker_fee_rate=0.00045,
        interval_seconds=1.0,
        max_cycles=1,
    )


def _preregistration(config: Path, ledger: Path) -> dict[str, object]:
    raw = ledger.read_bytes()
    return {
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "frozen_identity": {
            "observer_run_id": "observer-run",
            "prospective_start_ms": 0,
        },
        "ledger_prefix": {
            "path": str(ledger),
            "bytes": len(raw),
            "rows": 1,
            "sha256": sha256(raw).hexdigest(),
        },
        "source_evidence": [
            {
                "path": str(config),
                "sha256": sha256(config.read_bytes()).hexdigest(),
            }
        ],
    }


def _report(resolved: bool = False) -> dict[str, object]:
    executions = [{"decision_time_ms": 1, "net_return_bps": -69.0}] if resolved else []
    return {
        "state": "descriptive_exact_depth_evidence"
        if resolved
        else "awaiting_resolution",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
        },
        "identity": {"source_run_id": "observer-run"},
        "summary": {"resolved": len(executions)},
        "latest_attempts": [],
        "latest_executions": executions,
    }
