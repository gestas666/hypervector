"""Current-capital priority for the V58 report-only investigation queue."""

from __future__ import annotations

from types import SimpleNamespace

from hypervector.research.v58_current_investigation import (
    refresh_current_investigation,
)
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)
from hypervector.research.v58_eth_risk_lock_evidence import (
    attach_eth_risk_lock_evidence_to_ledger,
)

_ETH = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"
_BRENT = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"


def test_closed_eth_review_is_marked_complete_without_live_change() -> None:
    """Exact reconciliation must close the review task but retain research."""
    ledger: list[dict[str, object]] = [
        {
            "route": _ETH,
            "status": "being_tested",
            "evidence_state": "resolved_review_due",
        }
    ]
    payload = {
        "lifecycle_state": "closed",
        "minimum_additional_evidence": {"required_sides": ["long", "short"]},
        "historical_disposition": {"live_change_proposed": False},
    }

    attach_eth_risk_lock_evidence_to_ledger(ledger, payload)

    assert ledger[0]["review_status"] == "reviewed_no_live_change"
    assert ledger[0]["evidence_state"] == "reviewed_no_live_change"
    assert ledger[0]["status"] == "being_tested"


def test_open_live_capital_outranks_already_reviewed_eth() -> None:
    """The largest marked-to-stop open lifecycle is the immediate priority."""
    report = {
        "hypothesis_ledger": [
            {"route": _ETH, "review_status": "reviewed_no_live_change"}
        ]
    }
    lifecycles = (SimpleNamespace(route=_ETH, resolved=1, pending=0),)
    live_open = {
        "execution_authority": "none",
        "actual_exit_fills_claimed": False,
        "open_lifecycles": 1,
        "trades": [
            {
                "lifecycle_id": "xyz:BRENTOIL:520642502465",
                "strategy_id": _BRENT.split("|", 1)[0],
                "symbol": "xyz:BRENTOIL",
                "profit_protection_estimate": {"marked_to_stop_giveback_usd": 7.0},
            }
        ],
    }

    opportunities = SimpleNamespace(opportunities=())
    backend = SimpleNamespace(open_lifecycles=live_open)

    refresh_current_investigation(report, lifecycles, opportunities, backend)

    assert report["highest_value_next_investigation"] == {
        "route": _BRENT,
        "experiment": "reconcile_open_live_lifecycle",
        "why_now": "actual live capital is open under a frozen exit contract",
        "lifecycle_id": "xyz:BRENTOIL:520642502465",
        "priority_basis": "largest_marked_to_stop_giveback_usd",
        "marked_to_stop_giveback_usd": 7.0,
    }


def test_current_investigation_is_frozen_in_generator_identity() -> None:
    """Ranking logic must be source-bound like the digest it can change."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}

    assert "src/hypervector/research/v58_current_investigation.py" in paths
