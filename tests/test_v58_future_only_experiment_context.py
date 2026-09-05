"""V58 future-only experiment ledger tests."""

from __future__ import annotations

from importlib import import_module, util

from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)


_SP500 = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_BRENT = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"
_SP500_ID = "v58-sp500-lower-activation-profit-lock-future-only-v1"
_BRENT_ID = "v58-brentoil-profit-lock-future-only-v1"


def test_attaches_two_frozen_future_only_exit_experiments() -> None:
    """The central report must expose both current exit experiments separately."""
    module_name = "hypervector.research.v58_future_only_experiment_context"
    assert util.find_spec(module_name) is not None, "future-only context is missing"
    module = import_module(module_name)
    context = module.V58FutureOnlyExperimentContext(
        statuses=(_status(_SP500_ID, _SP500), _status(_BRENT_ID, _BRENT)),
        evidence={
            _SP500_ID: {"sha256": "a" * 64, "bytes": 10},
            _BRENT_ID: {"sha256": "b" * 64, "bytes": 11},
        },
        execution_authority="none",
        lineage={_SP500_ID: _sp500_lineage()},
    )
    report = _report()

    module.attach_v58_future_only_experiment_context(report, context)

    ledger = report["experiment_ledger"]
    assert [row["route"] for row in ledger] == [_SP500, _BRENT]
    assert all(row["status"] == "being_tested" for row in ledger)
    assert all(row["automatic_live_change"] is False for row in ledger)
    assert all(row["execution_authority"] == "none" for row in ledger)
    assert ledger[0]["prior_disposition"]["status"] == "reject"
    assert ledger[0]["revisit_basis"] == (
        "exact_v3_live_source_and_fill_contract_replaces_v1_l2_midpoint_proxy"
    )
    assert "prior_disposition" not in ledger[1]
    assert set(report["evidence"]["experiments"]) == {_SP500_ID, _BRENT_ID}
    assert set(report["evidence"]["experiment_lineage"]) == {_SP500_ID}


def test_rejects_sp500_revisit_without_prior_rejection_lineage() -> None:
    """A rejected SP500 lock must not silently reappear as a fresh experiment."""
    module = import_module("hypervector.research.v58_future_only_experiment_context")
    context = module.V58FutureOnlyExperimentContext(
        statuses=(_status(_SP500_ID, _SP500), _status(_BRENT_ID, _BRENT)),
        evidence={},
        execution_authority="none",
        lineage={},
    )

    try:
        module.attach_v58_future_only_experiment_context(_report(), context)
    except ValueError as exc:
        assert "SP500 prior rejection lineage" in str(exc)
    else:
        raise AssertionError("missing SP500 prior rejection lineage was accepted")


def test_continuous_generator_identity_covers_future_only_context() -> None:
    """Changing experiment parsing must invalidate continuous report provenance."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}
    assert "src/hypervector/research/v58_future_only_experiment_context.py" in paths


def _status(hypothesis_id: str, route: str) -> dict[str, object]:
    return {
        "hypothesis_id": hypothesis_id,
        "route": route,
        "provider_id": route.partition("|")[0],
        "symbol": route.partition("|")[2],
        "required_sides": ["long", "short"],
        "state": "awaiting_both_sides",
        "observed_at_utc": "2026-08-20T14:45:00+00:00",
        "age_seconds": 5.0,
        "freshness_status": "fresh",
        "evaluations": 80,
        "eligible": 2,
        "prospective_evaluations": 5,
        "prospective_eligible": 0,
        "unattributed_eligible_evaluations": 0,
        "open_lifecycles": 0,
        "closed_lifecycles": 0,
        "resolved_lifecycles": 0,
        "unresolved_lifecycles": 0,
        "side_progress": {
            side: {
                "attributable_entries": 0,
                "open_lifecycles": 0,
                "closed_lifecycles": 0,
                "resolved_lifecycles": 0,
                "minimum_met": False,
            }
            for side in ("long", "short")
        },
        "minimum_diagnostic_evidence_met": False,
        "live_change_supported": False,
    }


def _report() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "evidence": {},
        "change_proposals": [],
    }


def _sp500_lineage() -> dict[str, object]:
    return {
        "hypothesis_id": "sp500-breakout-profit-lock-l2-proxy",
        "status": "reject",
        "decision": "Keep the current SP500 exit contract unchanged.",
        "falsifier": "Exact venue trade and mark paths may update the proxy result.",
        "revisit_basis": (
            "exact_v3_live_source_and_fill_contract_replaces_v1_l2_midpoint_proxy"
        ),
        "new_evidence_scope": "future_only_both_sides_exact_costed_lifecycles",
        "source_evidence": {
            "path": "docs/research-journal/sp500-breakout-profit-lock-l2-proxy-v1.json",
            "sha256": "c" * 64,
            "bytes": 12,
        },
    }
