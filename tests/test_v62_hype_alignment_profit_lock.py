"""Tests for the V62 HYPE aligned-route exit review."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.v62_hype_alignment_profit_lock import (
    build_v62_hype_alignment_profit_lock,
    v62_candidate_orderbook_coverage,
)


def _aligned_market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=40, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_1m": "RANGE",
            "state_5m": "BREAKOUT",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    market.loc[index[5], "entry_side"] = "long"
    return market


def test_v62_exit_review_rejects_a60_without_measured_improvement() -> None:
    """An unchanged flat result cannot authorize the proposed live fix."""
    review = build_v62_hype_alignment_profit_lock(
        _aligned_market(),
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
        fold_count=2,
    )

    assert review.report["execution_authority"] == "none"
    assert review.report["automatic_promotion"] is False
    assert review.report["candidate_policy"]["policy_id"] == ("a60_floor15_trail30")
    assert review.report["disposition"] == "reject_in_development"
    assert (
        review.report["candidate"]["net_return_bps"]
        == (review.report["control"]["net_return_bps"])
    )
    assert set(review.trade_rows["policy_id"]) == {
        "aligned_live_exit_control",
        "a60_floor15_trail30",
    }


def test_v62_candidate_orderbook_coverage_requires_exact_entry_identity() -> None:
    """Only exact A60 entry identities count as local 0xArchive coverage."""
    trades = pd.DataFrame(
        [
            {
                "policy_id": "a60_floor15_trail30",
                "side": "long",
                "signal_time_utc": "2026-01-01T00:04:00+00:00",
                "entry_time_utc": "2026-01-01T00:05:00+00:00",
            },
            {
                "policy_id": "aligned_live_exit_control",
                "side": "short",
                "signal_time_utc": "2026-01-01T00:09:00+00:00",
                "entry_time_utc": "2026-01-01T00:10:00+00:00",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "side": "long",
                "signal_time_utc": "2026-01-01T00:04:00+00:00",
                "entry_time_utc": "2026-01-01T00:05:00+00:00",
                "status": "covered",
                "causal_covered": True,
                "execution_covered": True,
                "first_post_entry_delay_ms": 250,
            }
        ]
    )

    coverage = v62_candidate_orderbook_coverage(trades, audit)

    assert coverage == {
        "candidate_lifecycles": 1,
        "matched_audit_rows": 1,
        "causal_covered_rows": 1,
        "execution_covered_rows": 1,
        "status_counts": {"covered": 1},
        "maximum_first_post_entry_delay_ms": 250,
        "complete_candidate_entry_coverage": True,
    }
