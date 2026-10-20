"""Exact evidence bindings for the staged BTC and HYPE candidates."""

from pathlib import Path

import pytest

from hypervector.live import multi_asset_strategy_evidence
from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.hype_relaxed_contract import (
    HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads
from hypervector.live.multi_asset_strategy_evidence_models import (
    StrategyResearchEvidence,
)

_PROFILE = Path("tests/fixtures/profiles/evidence.toml")


def test_candidate_mappings_have_exact_non_gating_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reviewed identities bind exactly; every other mapping stays unreviewed."""
    expected_confidence = {
        (BTC_STRUCTURAL_FIXED60_STRATEGY, "BTC"): "medium",
        (HYPE_RELAXED_MATCHED_FIXED_STRATEGY, "HYPE"): "low",
    }
    for (strategy_id, symbol), confidence in expected_confidence.items():
        monkeypatch.setitem(
            multi_asset_strategy_evidence._EVIDENCE,
            (strategy_id, symbol),
            StrategyResearchEvidence(
                strategy_id,
                symbol,
                "prospective_candidate",
                confidence,
                "staged sample",
                "candidate summary",
                "evidence/candidate.json",
            ),
        )
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    payloads = strategy_evidence_payloads(config.providers)
    by_identity = {(row["strategy_id"], row["symbol"]): row for row in payloads}

    assert set(by_identity) == {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    for identity, evidence in by_identity.items():
        assert evidence["execution_effect"] == "report_only"
        if identity in expected_confidence:
            assert evidence["research_state"] == "prospective_candidate"
            assert evidence["confidence"] == expected_confidence[identity]
            assert evidence["evidence_source"] == "evidence/candidate.json"
        else:
            assert evidence["research_state"] == "unreviewed_exact_mapping"
            assert evidence["evidence_source"] == "none"
