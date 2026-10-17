"""Acceptance for the v49 cross-restart one-blocker disposition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence

_REPORT = Path("docs/research-journal/v49-cross-restart-filter-disposition.json")
_RUNS = [
    "bidirectional-observe-1786555674002",
    "bidirectional-observe-1786572851373",
    "bidirectional-observe-1786573011551",
]


def _load(path: Path) -> dict[str, object]:
    """Load one JSON object used by this source-bound acceptance."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _source(row: dict[str, object]) -> dict[str, object]:
    """Load and checksum one immutable one-blocker source report."""
    path = Path(str(row["path"]))
    assert row["sha256"] == file_evidence(path)["sha256"]
    return _load(path)


def _total_net(source: dict[str, object]) -> float:
    """Sum the source report's side-level net basis points."""
    by_side = source["by_side"]
    assert isinstance(by_side, dict)
    return sum(float(side["total_net_return_bps"]) for side in by_side.values())


@pytest.mark.evidence
def test_filter_disposition_is_report_only_and_source_bound() -> None:
    """Every conclusion must bind exact compatible-run evidence."""
    report = _load(_REPORT)

    assert report["mode"] == "report_only"
    assert report["execution_authority"] == "none"
    assert report["automatic_strategy_change"] is False
    assert report["compatible_run_ids"] == _RUNS
    assert report["profile_fingerprint"] == (
        "fddd3497f060950e45b598e735b8d0c40f7987161e78c7493f19ccfbf1e60a47"
    )

    evidence = report["evidence"]
    assert isinstance(evidence, list)
    assert len(evidence) == 9
    for row in evidence:
        assert isinstance(row, dict)
        source = _source(row)
        assert source["execution_authority"] == "none"
        assert source["report_only"] is True
        assert source["runtime_strategy_changed"] is False
        assert source["source"]["compatible_run_ids"] == _RUNS
        assert float(row["total_net_return_bps"]) == pytest.approx(_total_net(source))


def test_filter_relaxations_remain_rejected_by_exact_outcomes() -> None:
    """No filter may be loosened from these sparse counterfactuals."""
    report = _load(_REPORT)
    rows = {row["id"]: row for row in report["evidence"]}

    expected = {
        "sol_hourly_cross_15m": -150.9280465150627,
        "hype_compression_60m": -99.17895529881524,
        "hype_onset_15m": -85.24588377776666,
        "hype_onset_60m": -85.97336702309119,
        "btc_hulk_expansion_60m": -17.192047293142206,
        "eth_hourly_cross_15m": -38.74739521287732,
        "eth_hourly_cross_60m": 10.614998877258728,
        "eth_regime_15m": -1.6955082704234492,
        "eth_regime_60m": -13.842397625007383,
    }
    for evidence_id, total in expected.items():
        assert float(rows[evidence_id]["total_net_return_bps"]) == pytest.approx(total)
        assert rows[evidence_id]["decision"] == "retain_filter"

    eth_hourly = rows["eth_hourly_cross_60m"]
    assert eth_hourly["resolved"] == 2
    assert float(eth_hourly["net_excluding_largest_winner_bps"]) == pytest.approx(
        -5.326541485180471
    )
    assert report["portfolio_decision"] == "retain_current_entry_filters"
    assert report["btc_sweep_disposition"] == "not_isolated_retain_unchanged"


def test_disposition_states_scope_and_falsifiers() -> None:
    """The artifact must not overstate fixed-horizon diagnostics as fills."""
    report = _load(_REPORT)

    assert report["live_fills_claimed"] is False
    assert report["native_lifecycle_evaluated"] is False
    assert report["confidence"]["arithmetic"] == "high"
    assert report["confidence"]["future_profitability"] == "low"
    assert len(report["limitations"]) >= 4
    assert len(report["falsifiers"]) >= 3
