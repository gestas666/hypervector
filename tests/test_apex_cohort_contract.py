"""Contracts for the bounded Apex-derived research cohort."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.apex_cohort_contract import (
    APEX_CANDIDATES,
    RESEARCH_SEGMENTS,
    ApexCohortContract,
)


def test_cohort_contains_three_distinct_apex_families() -> None:
    assert [candidate.name for candidate in APEX_CANDIDATES] == [
        "apex_mean_reversion_v2",
        "apex_oi_trend_v2",
        "apex_regime_mm_v2",
    ]
    assert {candidate.family for candidate in APEX_CANDIDATES} == {
        "directional_mean_reversion",
        "directional_oi_trend",
        "two_sided_market_making",
    }


def test_contract_is_report_only_and_has_realistic_execution_assumptions() -> None:
    contract = ApexCohortContract()

    assert contract.initial_equity_usd == 15_000.0
    assert contract.execution_authority == "none"
    assert contract.report_only
    assert not contract.place_attempted
    assert contract.max_directional_positions_per_symbol == 1
    assert contract.maker_fee_rate == pytest.approx(0.00015)
    assert contract.taker_fee_rate == pytest.approx(0.00045)
    assert contract.submit_latency_ms == 50
    assert contract.cancel_latency_ms == 50


def test_research_budget_has_exactly_three_chronological_passes() -> None:
    assert [segment.name for segment in RESEARCH_SEGMENTS] == [
        "development",
        "validation",
        "robustness",
    ]
    assert all(
        left.end_utc <= right.start_utc
        for left, right in zip(RESEARCH_SEGMENTS, RESEARCH_SEGMENTS[1:])
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("initial_equity_usd", 0.0, "initial equity"),
        ("maker_fee_rate", -0.1, "fee rate"),
        ("taker_fee_rate", 1.0, "fee rate"),
        ("submit_latency_ms", -1, "latency"),
        ("max_directional_positions_per_symbol", 2, "one position"),
        ("execution_authority", "live", "execution authority"),
        ("report_only", False, "report-only"),
        ("place_attempted", True, "place attempts"),
    ],
)
def test_contract_rejects_unsafe_or_out_of_scope_values(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(ApexCohortContract(), **{field: value})
