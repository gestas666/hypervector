"""Tests for the outcome-blind Deribit instrument source amendment."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_SCRIPT = Path("scripts/v58_btc_deribit_option_flow_preregister_v4.py")


def test_v4_changes_only_source_metadata_recovery_and_status() -> None:
    """No candidate feature, strategy, economics, or partition may drift."""
    spec = importlib.util.spec_from_file_location("option_flow_v4", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load option-flow v4 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prior = _json(
        "docs/research-journal/"
        "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
    )
    audit = _json(
        "docs/research-journal/"
        "v58-btc-deribit-instrument-completeness-audit-20260822-v1.json"
    )

    revised = module.build_revision(
        prior,
        audit,
        audit_evidence={"sha256": "a" * 64},
        recorded_at_utc="2026-08-22T10:00:00Z",
    )

    for field in (
        "feature_contract",
        "strategy_contract",
        "economics",
        "partitions",
        "trial_arms",
        "acceptance",
        "multiple_testing_disclosure",
    ):
        assert revised[field] == prior[field]
    supplement = revised["source_contract"]["deribit_instruments"][
        "missing_name_supplement"
    ]
    assert supplement["expected_instrument_count"] == 563
    assert supplement["inference_permitted"] is False
    assert revised["candidate_signal_counts_inspected"] is False
    assert revised["live_change_authorized"] is False


def _json(path: str) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
