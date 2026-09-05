"""Tests for preregistered BTC liquidation development statistics."""

from __future__ import annotations

from decimal import Decimal

from hypervector.research.btc_liquidation_development_statistics import (
    EconomicObservation,
    economic_observations,
    holm_adjust,
    parse_development_arm_results,
    purge_arm_group,
    stationary_day_bootstrap,
    summarize_observations,
)


def _record(
    episode_id: str,
    decision_time_ms: int,
    entry_time_ms: int,
    pnl: str = "50.5",
) -> dict[str, object]:
    return {
        "schema_version": "btc_liquidation_development_arm_result_v1",
        "episode_id": episode_id,
        "partition": "development",
        "branch": "continuation_long",
        "arm": "5s_p95",
        "entry": {
            "status": "eligible",
            "blockers": [],
            "decision_time_ms": decision_time_ms,
            "decision_book_time_ms": entry_time_ms,
            "fill": {"quote_notional": "5050"},
        },
        "regime": {"primary_regime": "TREND_UP"},
        "outcomes": [
            {
                "horizon_ms": 300_000,
                "status": "resolved",
                "reason": None,
                "nominal_net_pnl_usd": pnl,
                "stressed_net_pnl_usd": "20.2",
            }
        ],
    }


def test_parser_uses_actual_entry_quote_as_return_denominator() -> None:
    """Executable return normalizes PnL by depth-walk entry quote, not 5000."""
    parsed = parse_development_arm_results((_record("a", 1_000, 1_100),))
    retained = purge_arm_group(
        parsed,
        branch="continuation_long",
        arm="5s_p95",
        overlap_horizon_ms=900_000,
    )
    observations = economic_observations(retained.retained, horizon_ms=300_000)

    assert len(observations) == 1
    assert observations[0].nominal_return_bps == Decimal("100.00")
    assert observations[0].stressed_return_bps == Decimal("40.00")


def test_overlap_purge_happens_before_primary_outcome_summary() -> None:
    """Suppress through retained entry plus 15 minutes in the exact group."""
    parsed = parse_development_arm_results(
        (
            _record("a", 1_000, 1_100),
            _record("b", 901_100, 901_200),
            _record("c", 901_101, 901_201),
        )
    )

    group = purge_arm_group(
        parsed,
        branch="continuation_long",
        arm="5s_p95",
        overlap_horizon_ms=900_000,
    )

    assert [row.episode_id for row in group.retained] == ["a", "c"]
    assert [row.episode_id for row in group.suppressed] == ["b"]


def test_stationary_day_bootstrap_is_seeded_and_null_centered() -> None:
    """Constant positive daily evidence yields a deterministic positive interval."""
    observations = tuple(
        EconomicObservation(
            str(day),
            "continuation_long",
            "5s_p95",
            day * 86_400_000,
            "TREND_UP",
            Decimal("10"),
            Decimal("5"),
            Decimal("5"),
        )
        for day in range(1, 15)
    )

    first = stationary_day_bootstrap(
        observations,
        value="nominal_return_bps",
        expected_block_days=7,
        resamples=1_000,
        seed=20260822,
    )
    second = stationary_day_bootstrap(
        observations,
        value="nominal_return_bps",
        expected_block_days=7,
        resamples=1_000,
        seed=20260822,
    )

    assert first == second
    assert first.point_estimate == 10.0
    assert first.lower == 10.0
    assert first.upper == 10.0
    assert first.one_sided_p_value == 1 / 1001


def test_holm_adjustment_and_summary_concentration_are_exact() -> None:
    """Holm controls two branches and concentration uses positive PnL only."""
    adjusted = holm_adjust({"continuation_long": 0.01, "exhaustion_reclaim_long": 0.04})
    observations = (
        EconomicObservation(
            "a",
            "continuation_long",
            "5s_p95",
            1,
            "RANGE",
            Decimal("1"),
            Decimal("1"),
            Decimal("30"),
        ),
        EconomicObservation(
            "b",
            "continuation_long",
            "5s_p95",
            2,
            "RANGE",
            Decimal("1"),
            Decimal("1"),
            Decimal("70"),
        ),
        EconomicObservation(
            "c",
            "continuation_long",
            "5s_p95",
            3,
            "RANGE",
            Decimal("-1"),
            Decimal("-1"),
            Decimal("-20"),
        ),
    )
    summary = summarize_observations(observations)

    assert adjusted == {
        "continuation_long": 0.02,
        "exhaustion_reclaim_long": 0.04,
    }
    assert summary["largest_positive_pnl_contribution"] == Decimal("0.7")
    assert summary["profit_factor"] == Decimal("5")
