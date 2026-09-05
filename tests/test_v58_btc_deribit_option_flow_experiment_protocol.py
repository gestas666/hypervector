"""Tests for the outcome-blind BTC option-flow experiment protocol."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_SCRIPT = Path("scripts/v58_btc_deribit_option_flow_experiment_protocol.py")


def _module() -> object:
    spec = importlib.util.spec_from_file_location("option_flow_protocol", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load option-flow protocol script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_freezes_contiguous_folds_and_bootstrap_before_outcomes() -> None:
    """The exact evaluation mechanics must be immutable and outcome-blind."""
    module = _module()
    preregistration = json.loads(
        Path(
            "docs/research-journal/"
            "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
        ).read_text(encoding="utf-8")
    )

    protocol = module.build_protocol(
        preregistration,
        preregistration_evidence={"sha256": "a" * 64},
        recorded_at_utc="2026-08-22T09:00:00Z",
    )

    folds = protocol["development_folds"]
    assert len(folds) == 5
    assert folds[0]["entry_start_utc"] == "2025-10-01T00:00:00Z"
    assert folds[-1]["entry_end_exclusive_utc"] == "2025-12-01T00:00:00Z"
    assert all(
        left["entry_end_exclusive_utc"] == right["entry_start_utc"]
        for left, right in zip(folds[:-1], folds[1:], strict=True)
    )
    assert protocol["pooled_oos_trade_bootstrap"]["resamples"] == 10_000
    assert protocol["pooled_oos_trade_bootstrap"]["seed"] == 58
    assert protocol["outcome_blindness"]["candidate_trade_outcomes_inspected"] is False
    assert protocol["authority"]["live_change_authorized"] is False
