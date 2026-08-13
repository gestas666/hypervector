"""Exact report-only evidence bindings for the active v25 HIP-3 routes."""

from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)

SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"
BREAKOUT_INDEX_FRESH15_V3 = (
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
)


def test_index_routes_report_latest_exact_research_decision() -> None:
    """New SPCX attribution supersedes its earlier aggregate diagnostic."""
    swing = strategy_research_evidence(SWING_INDEX, "xyz:SPCX")
    breakout = strategy_research_evidence(BREAKOUT_INDEX, "xyz:SP500")

    assert swing.research_state == "side_timing_set_falsified_new_mechanism_required"
    assert "eight timing/side arms" in swing.summary
    assert "new causal mechanism identity" in swing.summary
    assert breakout.research_state == "v25_lifecycle_diagnostic_positive_unrouted"
    assert "+$0.6615" in breakout.summary
    assert "PF 1.4539" in breakout.summary
    assert swing.evidence_source == (
        "docs/research-journal/spcx-side-mechanism-attribution-v1.json"
    )
    assert swing.execution_effect == "report_only"
    assert breakout.execution_effect == "report_only"


def test_fresh15_v3_index_route_discloses_prospective_trial_limits() -> None:
    """The repaired adapter cannot inherit retired-v2 or legacy-v1 evidence."""
    for symbol in ("xyz:SP500", "xyz:SPCX"):
        evidence = strategy_research_evidence(BREAKOUT_INDEX_FRESH15_V3, symbol)

        assert evidence.research_state == (
            "prospective_v3_technical_parity_live_outcomes_unresolved"
        )
        assert evidence.confidence == "low"
        assert "no resolved v3 live outcomes" in evidence.cadence
        assert "does not establish profitable edge" in evidence.summary
        assert "v2" in evidence.summary
        assert evidence.evidence_source == (
            "docs/research-journal/hip3-index-preclose-pressure-parity-v3.json"
        )
        assert evidence.execution_effect == "report_only"


def test_commodity_swing_preserves_distinct_v25_stress_results() -> None:
    """The shared Swing identity cannot hide superseding GOLD attribution."""
    expected = {
        "xyz:SNDK": (
            "v25_lifecycle_diagnostic_stress_negative",
            "PF 0.6600",
            "-$6.6113",
        ),
        "xyz:GOLD": (
            "side_timing_set_falsified_new_mechanism_required",
            "Zero of eight",
            "new causal mechanism identity",
        ),
        "xyz:BRENTOIL": (
            "v25_lifecycle_diagnostic_stress_negative",
            "PF 0.6173",
            "-$6.4518",
        ),
    }

    for symbol, (state, *fragments) in expected.items():
        evidence = strategy_research_evidence(SWING_COMMODITY, symbol)
        assert evidence.research_state == state
        assert all(fragment in evidence.summary for fragment in fragments)
        if symbol == "xyz:GOLD":
            assert evidence.evidence_source == (
                "docs/research-journal/hip3-entry-timing-challenger-v3.json"
            )
        else:
            assert "route aggregate" in evidence.summary


def test_commodity_breakout_reports_stress_failure_for_every_symbol() -> None:
    """A nominal SNDK gain cannot hide the v25 stress reversal."""
    expected = {
        "xyz:SNDK": ("nominal +$4.5585", "stress -$3.4611", "PF 0.8077"),
        "xyz:GOLD": ("stress -$1.6603", "PF 0.8097"),
        "xyz:BRENTOIL": ("stress -$4.4700", "PF 0.6293"),
    }

    for symbol, fragments in expected.items():
        evidence = strategy_research_evidence(BREAKOUT_COMMODITY, symbol)
        assert evidence.research_state == "v25_lifecycle_diagnostic_stress_negative"
        assert "fixed-80/24h" in evidence.summary
        assert all(fragment in evidence.summary for fragment in fragments)
