"""Exact evidence bindings for the staged BTC and HYPE candidates."""

from pathlib import Path

from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.hype_relaxed_contract import (
    HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_evidence_payloads,
    strategy_research_evidence,
)

_PROFILE = Path("tests/fixtures/profiles/multi_asset_bidirectional_evidence_candidate_v4.toml")


def test_candidate_mappings_have_exact_non_gating_evidence() -> None:
    """Staged identities cannot fall through to a generic unreviewed record."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    payloads = strategy_evidence_payloads(config.providers)
    by_identity = {(row["strategy_id"], row["symbol"]): row for row in payloads}

    expected_confidence = {
        (BTC_STRUCTURAL_FIXED60_STRATEGY, "BTC"): "medium",
        (HYPE_RELAXED_MATCHED_FIXED_STRATEGY, "HYPE"): "low",
    }
    for identity, confidence in expected_confidence.items():
        evidence = by_identity[identity]
        assert evidence["research_state"] != "unreviewed_exact_mapping"
        assert evidence["confidence"] == confidence
        assert evidence["execution_effect"] == "report_only"


def test_btc_evidence_discloses_retrospective_and_prospective_limits() -> None:
    """The resolved forward rejection must supersede the attractive history."""
    evidence = strategy_research_evidence(BTC_STRUCTURAL_FIXED60_STRATEGY, "BTC")

    assert evidence.research_state == "prospective_rejected_n11"
    assert "PF 0.4794" in evidence.summary
    assert "-77.3943 bps" in evidence.summary
    assert "overlapped" in evidence.summary


def test_hype_v4_evidence_uses_the_matched_exit_batch() -> None:
    """V4 is bound to matched fixed-horizon outcomes, not failed target-first PnL."""
    evidence = strategy_research_evidence(
        HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
        "HYPE",
    )

    assert "N3" in evidence.summary
    assert "PF 1.1887" in evidence.summary
    assert "+8.9711 bps" in evidence.summary
    assert "all-long" in evidence.summary
