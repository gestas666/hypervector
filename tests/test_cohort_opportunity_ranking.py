"""Contracts for transparent continuous-research opportunity ranking."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_opportunity_ranking import (
    rank_research_opportunities,
)


def test_ranking_uses_information_confidence_complexity_and_downside() -> None:
    queue = [
        _row("mechanism|HYPE", "new_mechanic_version_required", 1),
        _row("live|SP500", "collect_both_side_live_execution", 3),
        _row("parity|SPCX", "collect_and_resolve_source_transport_parity", 2),
    ]
    scores = {
        "mechanism|HYPE": {"confidence": "high"},
        "live|SP500": {"confidence": "medium"},
        "parity|SPCX": {"confidence": "low"},
    }

    ranking = rank_research_opportunities(queue, scores)

    assert [row["route"] for row in ranking] == [
        "parity|SPCX",
        "live|SP500",
        "mechanism|HYPE",
    ]
    assert ranking[0]["expected_economic_value"] == (
        "unquantified_until_compatible_forward_lifecycles"
    )
    assert ranking[0]["expected_information_value"] == "very_high"
    assert ranking[0]["confidence"] == "low"
    assert ranking[0]["implementation_complexity"] == "low_report_only"
    assert ranking[0]["downside"] == "source_mismatch_can_invalidate_economics"
    assert ranking[0]["validation_priority"] == 1
    assert ranking[0]["automatic_live_change"] is False


def test_equal_information_prefers_confidence_then_lower_complexity() -> None:
    queue = [
        _row("low-confidence|BTC", "collect_both_side_live_execution", 1),
        _row("high-confidence|ETH", "collect_both_side_live_execution", 1),
    ]
    scores = {
        "low-confidence|BTC": {"confidence": "low"},
        "high-confidence|ETH": {"confidence": "high"},
    }

    ranking = rank_research_opportunities(queue, scores)

    assert ranking[0]["route"] == "high-confidence|ETH"
    assert ranking[0]["rank_basis"]["confidence_class"] == 3


def test_source_bound_prior_rank_precedes_confidence_for_same_experiment() -> None:
    """A reviewed evidence priority must not be reversed by a generic label."""
    queue = [
        _row("index|SP500", "collect_both_side_live_execution", 1),
        _row("range|SOL", "collect_both_side_live_execution", 3),
    ]
    scores = {
        "index|SP500": {"confidence": "low"},
        "range|SOL": {"confidence": "medium"},
    }

    ranking = rank_research_opportunities(queue, scores)

    assert ranking[0]["route"] == "index|SP500"


def test_long_entry_diagnosis_outranks_passive_collection() -> None:
    """A causal loss diagnosis has higher information value than waiting."""
    queue = [
        _row("spcx|SPCX", "diagnose_long_entry_quality", 1),
        _row("hype|HYPE", "collect_both_side_live_execution", 2),
    ]
    scores = {
        "spcx|SPCX": {"confidence": "low"},
        "hype|HYPE": {"confidence": "medium"},
    }

    ranking = rank_research_opportunities(queue, scores)

    assert ranking[0]["route"] == "spcx|SPCX"
    assert ranking[0]["expected_information_value"] == "very_high"
    assert ranking[0]["automatic_live_change"] is False


def test_low_to_medium_confidence_is_ranked_conservatively() -> None:
    """A live evidence label must remain valid without overstating confidence."""
    queue = [_row("tuned|BTC", "collect_side_specific_evidence", 1)]

    ranking = rank_research_opportunities(
        queue, {"tuned|BTC": {"confidence": "low_to_medium"}}
    )

    assert ranking[0]["confidence"] == "low_to_medium"
    assert ranking[0]["rank_basis"]["confidence_class"] == 1


def test_unknown_confidence_fails_closed() -> None:
    queue = [_row("route|BTC", "collect_both_side_live_execution", 1)]

    with pytest.raises(ValueError, match="unsupported opportunity confidence"):
        rank_research_opportunities(queue, {"route|BTC": {"confidence": "certain"}})


def _row(route: str, experiment: str, rank: int) -> dict[str, object]:
    return {
        "route": route,
        "next_experiment": experiment,
        "research_rank": rank,
    }
