"""Current route evidence must reflect the latest immutable journal decisions."""

from hypervector.live.btc_structural_contract import (
    BTC_STRUCTURAL_FIXED60_STRATEGY,
)
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)

HULK = "hulk_expansion_bidirectional_tuned_v2"
RANGE = "range_onset_bidirectional_v1"


def test_native_hulk_transfer_routes_are_no_longer_unreviewed() -> None:
    """ETH and HYPE must expose the completed exact-rule transfer rejection."""
    for symbol, profit_factor in (("ETH", "0.5919"), ("HYPE", "0.4639")):
        evidence = strategy_research_evidence(HULK, symbol)

        assert evidence.research_state == "historical_native_transfer_negative"
        assert profit_factor in evidence.summary
        assert "both long and short" in evidence.summary
        assert evidence.evidence_source.endswith(
            "hulk-eth-hype-native-transfer-v1.json"
        )


def test_range_timeframe_routes_expose_latest_side_specific_decision() -> None:
    """BTC and HYPE must use the resolved yearly route audit, not fallback text."""
    btc = strategy_research_evidence(RANGE, "BTC")
    hype = strategy_research_evidence(RANGE, "HYPE")

    assert btc.research_state == "historical_timeframe_route_negative"
    assert "106 trades" in btc.summary
    assert "both directions" in btc.summary
    assert hype.research_state == "historical_timeframe_route_contradictory"
    assert "pseudo-holdout" in hype.summary
    assert "long" in hype.summary
    assert btc.evidence_source == hype.evidence_source
    assert btc.evidence_source.endswith(
        "range-onset-btc-hype-timeframe-transfer-v1.json"
    )


def test_btc_structural_evidence_includes_resolved_forward_rejection() -> None:
    """The TUI cannot continue advertising the obsolete prospective-N0 state."""
    evidence = strategy_research_evidence(BTC_STRUCTURAL_FIXED60_STRATEGY, "BTC")

    assert evidence.research_state == "prospective_rejected_n11"
    assert "11" in evidence.cadence
    assert "PF 0.4794" in evidence.summary
    assert "-77.3943 bps" in evidence.summary
    assert evidence.evidence_source.endswith("btc-structural-continuation-v1.json")
