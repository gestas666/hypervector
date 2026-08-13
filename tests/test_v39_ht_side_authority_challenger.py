"""Exact v39 HT side-authority challenger tests."""

from __future__ import annotations

from hypervector.research.v39_forward_evidence_contract import PROFILE_FINGERPRINT
from hypervector.research.v39_ht_side_authority_challenger import (
    build_v39_ht_side_authority_challenger,
)

_RUN_ID = "bidirectional-live-1786453934555"


def test_three_frozen_side_variants_preserve_aligned_and_opposed_onsets() -> None:
    evaluations = (
        _evaluation("ETH", 1_000, "short", "short"),
        _evaluation("BTC", 2_000, "short", "long"),
        _evaluation("SOL", 3_000, "short", None, eligible=False),
    )

    report = build_v39_ht_side_authority_challenger(
        evaluations,
        run_id=_RUN_ID,
        profile_fingerprint=PROFILE_FINGERPRINT,
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["summary"] == {
        "eligible_onsets": 2,
        "aligned_onsets": 1,
        "opposed_onsets": 1,
        "unavailable_onsets": 0,
        "structural_variant_entries": 2,
        "breakout_variant_entries": 2,
        "agree_only_variant_entries": 1,
        "agree_only_no_trades": 1,
    }
    decisions = report["decisions"]
    assert decisions[0]["variants"]["structural_side"] == {
        "action": "enter_short",
        "side": "short",
    }
    assert decisions[0]["variants"]["agree_only"] == {
        "action": "enter_short",
        "side": "short",
    }
    assert decisions[1]["variants"]["breakout_side"] == {
        "action": "enter_long",
        "side": "long",
    }
    assert decisions[1]["variants"]["agree_only"] == {
        "action": "no_trade",
        "side": None,
    }
    assert len(report["source_evaluations_sha256"]) == 64


def _evaluation(
    symbol: str,
    decision_time_ms: int,
    structural_side: str,
    breakout_side: str | None,
    *,
    eligible: bool = True,
) -> dict[str, object]:
    relation = (
        "unavailable"
        if breakout_side is None
        else "aligned"
        if structural_side == breakout_side
        else "opposed"
    )
    return {
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "reference_price": 100.0,
        "eligible": eligible,
        "side": structural_side,
        "decision_action": f"enter_{structural_side}" if eligible else "hold",
        "readiness": {
            "metrics": {
                "breakout_onset": eligible,
                "structural_direction": structural_side,
                "breakout_side": breakout_side,
                "breakout_side_relation": relation,
            }
        },
    }
