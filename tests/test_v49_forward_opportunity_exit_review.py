"""Acceptance for the frozen v49 opportunity and exit review."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

_REPORT = Path(
    "docs/research-journal/v49-forward-opportunity-exit-review-20260813-v1.json"
)
_OPPORTUNITY = Path(
    "data/logs/research/bidirectional_cohort/"
    "v49_observer_opportunity_checkpoint_20260813T0500Z_v1.json"
)
_SOL = Path("data/logs/research/v49_sol_profit_lock_forward_20260813_v4.json")


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _provider(source: dict[str, object], key: str) -> dict[str, object]:
    audit = source["audit"]
    assert isinstance(audit, dict)
    outcomes = audit["signal_outcomes"]
    assert isinstance(outcomes, dict)
    providers = outcomes["by_provider_symbol"]
    assert isinstance(providers, dict)
    value = providers[key]
    assert isinstance(value, dict)
    return value


def test_review_is_source_bound_and_non_executable() -> None:
    """The review must bind exact observer and SOL lifecycle artifacts."""
    report = _load(_REPORT)
    assert report["schema_version"] == "v49_forward_opportunity_exit_review_v1"
    assert report["contract"] == {
        "automatic_live_promotion": False,
        "execution_authority": "none",
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    for key, path in {
        "opportunity_checkpoint": _OPPORTUNITY,
        "sol_forward": _SOL,
    }.items():
        evidence = report["evidence"]
        assert isinstance(evidence, dict)
        source = evidence[key]
        assert isinstance(source, dict)
        assert source == {"path": str(path), "sha256": _digest(path)}


def test_review_reconciles_independent_sixty_minute_near_misses() -> None:
    """Relaxation findings must equal non-overlapping source outcomes."""
    report = _load(_REPORT)
    source = _load(_OPPORTUNITY)
    for key, row in report["entry_gate_review"].items():
        assert isinstance(row, dict)
        provider = _provider(source, key)
        horizon = provider["horizons"]["60"]["independent_opportunity_capture"]
        assert row["resolved_near_misses"] == horizon["resolved"]
        assert row["cost_clearing_closes"] == horizon["cost_clearing_close_count"]
        assert (
            row["mean_after_cost_bps"]
            == horizon["mean_close_after_estimated_friction_bps"]
        )
        assert (
            row["mean_ex_largest_after_cost_bps"]
            == horizon["mean_excluding_largest_close_after_estimated_friction_bps"]
        )


def test_review_does_not_relax_an_entry_gate_from_negative_near_misses() -> None:
    """Sparse or negative one-blocker paths cannot justify broad entry relaxation."""
    report = _load(_REPORT)
    gate = report["entry_gate_disposition"]
    assert gate["decision"] == "retain_frozen_v49_entry_gates"
    assert gate["routes_with_positive_ex_largest_mean"] == []
    assert gate["liquidity_sweep_state"] == "no_resolved_near_miss_evidence"
    assert gate["hype_state"] == "near_flat_mean_but_negative_ex_largest"


def test_review_reconciles_sol_giveback_and_predeclared_profit_locks() -> None:
    """The exit diagnosis must preserve current and causal challenger economics."""
    report = _load(_REPORT)
    source = _load(_SOL)
    attempt = source["exact_visible_depth_lifecycle"]["latest_attempts"][0]
    exit_review = report["sol_exit_review"]
    assert exit_review["native_status"] == attempt["status"] == "exit_pending"
    assert exit_review["native_marked_net_bps"] == attempt["current_net_return_bps"]
    assert (
        exit_review["native_marked_net_usd"] == attempt["current_simulated_net_pnl_usd"]
    )
    policies = source["profit_lock_challenger"]["latest_results"][0]["policies"]
    for policy_id, row in exit_review["predeclared_profit_locks"].items():
        economics = policies[policy_id]["counterfactual_economics"]
        assert (
            row["estimated_net_usd_ex_funding"]
            == economics["estimated_net_pnl_excluding_funding_usd"]
        )
        assert (
            row["trigger_timestamp_ms"] == policies[policy_id]["trigger_timestamp_ms"]
        )


def test_review_keeps_exit_change_report_only_until_independent_outcomes() -> None:
    """One giveback supports a challenger, not an automatic live mutation."""
    report = _load(_REPORT)
    disposition = report["exit_disposition"]
    assert disposition["native_exit_changed"] is False
    assert disposition["decision"] == "continue_predeclared_profit_lock_forward"
    assert disposition["planned_comparison_checkpoint_lifecycles"] == 5
    assert disposition["checkpoint_is_performance_gate"] is False
    assert disposition["selection_metric"] == (
        "after_cost_net_and_drawdown_stability_excluding_largest_winner"
    )
