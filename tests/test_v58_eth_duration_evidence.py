"""Continuous-report integration for immutable V58 ETH duration evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


_MODULE = Path("src/hypervector/research/v58_eth_duration_evidence.py")
_ROUTE = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"


def test_attaches_captured_duration_evidence_to_eth_hypothesis(
    tmp_path: Path,
) -> None:
    """A source-bound checkpoint must become explicit report-only evidence."""
    module = _module()
    source = tmp_path / "duration.json"
    source.write_text(json.dumps(_artifact()), encoding="utf-8")
    report = _report()

    module.attach_v58_eth_duration_evidence(report, source)

    context = report["eth_duration_checkpoint_context"]
    assert context["status"] == "captured"
    assert context["fixed_240m"]["simulated_net_pnl_usd"] == 23.0
    assert context["fixed_480m"]["simulated_net_pnl_usd"] == 17.5
    assert context["fixed_240m_minus_480m_usd"] == 5.5
    assert context["execution_authority"] == "none"
    assert context["strategy_change_supported"] is False
    eth = report["hypothesis_ledger"][0]
    assert eth["duration_checkpoint_status"] == "captured_single_open_path"
    assert eth["duration_checkpoint_evidence"] == context
    evidence = report["evidence"]["eth_duration_checkpoint_context"]
    assert evidence["path"] == str(source.resolve())
    assert evidence["bytes"] == source.stat().st_size


def test_missing_duration_artifact_stays_explicitly_unavailable(tmp_path: Path) -> None:
    """Before the boundary, absence must not become measured zero evidence."""
    module = _module()
    report = _report()

    module.attach_v58_eth_duration_evidence(report, tmp_path / "missing.json")

    assert report["eth_duration_checkpoint_context"] == {
        "status": "not_available",
        "reason": "duration_checkpoint_not_published",
        "execution_authority": "none",
        "strategy_change_supported": False,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("execution_authority", "live", "authority"),
        ("strategy_change_supported", True, "authority"),
    ),
)
def test_rejects_success_shaped_duration_authority(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    """A duration artifact cannot smuggle live or promotion authority."""
    module = _module()
    payload = _artifact()
    payload[field] = value
    source = tmp_path / "duration.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        module.attach_v58_eth_duration_evidence(_report(), source)


def test_rejects_inconsistent_duration_economics(tmp_path: Path) -> None:
    """Published net return and notional must reconcile to simulated dollars."""
    module = _module()
    payload = _artifact()
    payload["duration_checkpoints"]["fixed_480m"]["simulated_net_pnl_usd"] = 99.0
    source = tmp_path / "duration.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="economics"):
        module.attach_v58_eth_duration_evidence(_report(), source)


def _module() -> ModuleType:
    assert _MODULE.is_file(), "V58 ETH duration evidence module is missing"
    spec = spec_from_file_location("v58_eth_duration_evidence", _MODULE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report() -> dict[str, object]:
    return {
        "hypothesis_ledger": [{"route": _ROUTE, "symbol": "ETH"}],
        "evidence": {},
    }


def _artifact() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v58_eth_fixed_entry_duration_checkpoint_v1",
        "execution_authority": "none",
        "historical_optimum_claim": False,
        "strategy_change_supported": False,
        "source_lifecycle": {
            "source_run_id": "observer-run",
            "strategy_id": _ROUTE.split("|", 1)[0],
            "candidate_strategy_id": (
                "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward"
            ),
            "symbol": "ETH",
            "side": "long",
            "decision_time_ms": 1_000,
            "entry_time_ms": 2_000,
        },
        "duration_checkpoints": {
            "fixed_240m": _checkpoint(240, 23.0),
            "fixed_480m": _checkpoint(480, 17.5),
        },
        "retained_control": {
            "maximum_hold_minutes": 720,
            "state": "awaiting_resolution",
            "deadline_time_ms": 43_202_000,
        },
        "retained_control_snapshot": {
            "status": "exit_pending",
            "actual_exit_fill_claim": False,
            "net_return_scope": "exact_depth_fee_and_funding",
        },
    }


def _checkpoint(minutes: int, pnl: float) -> dict[str, object]:
    return {
        "status": "resolved",
        "exit_reason": "maximum_hold",
        "maximum_hold_minutes": minutes,
        "entry_notional_usd": 750.0,
        "net_return_bps": pnl / 750.0 * 10_000.0,
        "simulated_net_pnl_usd": pnl,
        "net_return_scope": "exact_depth_fee_and_funding",
    }
