"""Exact evidence bindings for the V58 commodity mappings."""

from __future__ import annotations

import pytest

from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)

_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_SOURCE = (
    "docs/research-journal/v58-eight-asset-opportunity-coverage-audit-20260819-v1.json"
)


@pytest.mark.parametrize(
    ("symbol", "state", "summary_fragment"),
    [
        (
            "xyz:SNDK",
            "identity_and_side_mismatch_no_current_edge_evidence",
            "two long protective-stop losses",
        ),
        (
            "xyz:BRENTOIL",
            "older_route_negative_and_current_identity_unmeasured",
            "-$0.232469 net",
        ),
    ],
)
def test_v58_commodity_routes_use_completed_audit_dispositions(
    symbol: str,
    state: str,
    summary_fragment: str,
) -> None:
    """Completed commodity reviews cannot regress to unreviewed evidence."""
    evidence = strategy_research_evidence(_STRATEGY, symbol)

    assert evidence.research_state == state
    assert evidence.confidence == "low"
    assert summary_fragment in evidence.summary
    assert evidence.evidence_source == _SOURCE
    assert evidence.execution_effect == "report_only"
