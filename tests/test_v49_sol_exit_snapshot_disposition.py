"""Acceptance for the latest unresolved v49 SOL exit snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence

_REPORT = Path("docs/research-journal/v49-strategy-repair-disposition.json")
_SNAPSHOT = Path("data/logs/research/v49_sol_profit_lock_forward_20260813_v3.json")


def _load(path: Path) -> dict[str, object]:
    """Load one JSON object used by the source-bound acceptance."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_disposition_binds_latest_unresolved_sol_exit_snapshot() -> None:
    """Native recovery must remain visible without selecting a policy."""
    report = _load(_REPORT)
    source = _load(_SNAPSHOT)
    decision = report["observer_eligible_lifecycle_disposition"]
    exact = source["exact_visible_depth_lifecycle"]["latest_attempts"][0]
    policies = source["profit_lock_challenger"]["latest_results"][0]["policies"]

    assert decision["profit_lock_forward_latest_snapshot"] == str(_SNAPSHOT)
    assert (
        decision["profit_lock_forward_latest_snapshot_sha256"]
        == (file_evidence(_SNAPSHOT)["sha256"])
    )
    assert exact["current_net_return_bps"] == pytest.approx(33.27160713319444)
    assert _delta(policies, "a25_floor15_trail10") > 0.0
    assert _delta(policies, "a60_floor15_trail30") < 0.0
    assert decision["automatic_strategy_change"] is False
    assert str(_SNAPSHOT) in report["evidence_paths"]


def _delta(policies: object, policy: str) -> float:
    """Return one policy's estimated change from the native boundary."""
    assert isinstance(policies, dict)
    economics = policies[policy]["counterfactual_economics"]
    return float(economics["estimated_minus_current_exit_net_excluding_funding_usd"])
