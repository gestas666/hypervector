"""Observer-window provenance for the first V58 ETH close report."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.v58_eth_live_close_reconciliation_io import (
    load_v58_eth_live_close_reconciliation,
)
from test_v58_eth_live_close_reconciliation import _source_files
from v58_eth_close_source_fixtures import observer_window_provenance


def test_close_report_discloses_invalid_aggregate_observer_window(
    tmp_path: Path,
) -> None:
    """A resolved lifecycle must not rehabilitate its incomplete source window."""
    paths = _source_files(tmp_path)
    provenance = tmp_path / "observer_provenance.json"
    provenance.write_text(json.dumps(observer_window_provenance()), encoding="utf-8")
    evidence = file_evidence(provenance)

    report = load_v58_eth_live_close_reconciliation(
        paths["preregistration"],
        expected_preregistration_sha256=paths["preregistration_sha256"],
        continuous_path=paths["continuous"],
        venue_path=paths["venue"],
        observer_status_path=paths["observer_status"],
        observer_provenance_path=provenance,
        expected_observer_provenance_sha256=str(evidence["sha256"]),
        generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )

    source = report["observer_window_provenance"]
    assert source["aggregate_window_technical_complete"] is False
    assert source["single_implementation_window"] is False
    assert source["aggregate_profitability_claim_supported"] is False
    assert source["exact_lifecycle_comparison_supported"] is True
    assert source["technical_gaps"] == ["observer_heartbeat_gap_exceeds_entry_delay"]
    assert report["source_evidence"]["observer_window_provenance"] == {
        "path": str(provenance.resolve()),
        **evidence,
    }
