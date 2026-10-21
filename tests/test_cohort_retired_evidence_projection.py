"""Retired-asset provenance across bounded checkpoint refreshes."""

from __future__ import annotations

from copy import deepcopy

from hypervector.research.cohort_checkpoint_history import (
    merge_complete_historical_projection,
)
from test_cohort_live_checkpoint import _historical_projection_fixture


def test_bounded_refresh_retains_complete_retired_asset_evidence() -> None:
    """Cached all-time history must retain its retired-ledger provenance."""
    bounded = _historical_projection_fixture("2026-08-12T05:45:00+00:00")
    complete = _historical_projection_fixture("2026-08-12T05:44:30+00:00")
    bounded["evidence"] = {
        "cohort": {"path": "current/decisions.jsonl"},
        "assets": {"BTC": {"path": "current/btc.jsonl"}},
        "retired_assets": {},
    }
    complete["evidence"] = {
        "cohort": {"path": "prior/decisions.jsonl"},
        "assets": {"BTC": {"path": "prior/btc.jsonl"}},
        "retired_assets": {"xyz:DDD": {"path": "prior/xyz:ddd.jsonl"}},
    }
    complete_before = deepcopy(complete)

    merged = merge_complete_historical_projection(bounded, complete)

    assert merged["evidence"]["cohort"] == bounded["evidence"]["cohort"]
    assert merged["evidence"]["assets"] == bounded["evidence"]["assets"]
    assert merged["evidence"]["retired_assets"] == {
        "xyz:DDD": {"path": "prior/xyz:ddd.jsonl"}
    }
    assert complete == complete_before
