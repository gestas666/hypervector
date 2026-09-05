"""Causal counterfactual outcome evidence for cohort provider evaluations."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy

import pytest

from cohort_signal_outcomes_fixtures import (
    DECISION_MS as _DECISION_MS,
    RUN_ID as _RUN_ID,
    STRATEGY as _STRATEGY,
    asset_rows as _asset_rows,
    cohort_rows as _cohort_rows,
    first_object as _first_object,
    nested_list as _nested_list,
    payload as _payload,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_signal_outcomes import (
    build_provider_forward_diagnostics,
)


def test_eligible_long_evaluation_resolves_without_claiming_a_fill() -> None:
    """Completed future candles diagnose a signal without inventing execution."""
    report = audit_multi_asset_live_run(
        _cohort_rows(),
        {"BTC": _asset_rows()},
        run_id=_RUN_ID,
    )

    outcomes = report["signal_outcomes"]
    assert outcomes["contract"] == {
        "counterfactual_only": True,
        "fills_assumed": False,
        "pnl_claimed": False,
        "execution_authority": "none",
        "model_trained": False,
        "thresholds_selected": False,
        "configured_direction_attribution": "counterfactual_only",
        "path_start_policy": ("first_full_minute_at_or_after_candidate_availability"),
    }
    assert outcomes["evaluations"] == 1
    assert outcomes["eligible_evaluations"] == 1
    bucket = outcomes["by_provider_symbol"][f"{_STRATEGY}|BTC"]
    assert bucket["by_side"] == {
        "long": {"evaluations": 1, "eligible_evaluations": 1},
        "short": {"evaluations": 0, "eligible_evaluations": 0},
    }
    horizon = bucket["horizons"]["5"]
    assert horizon["resolved"] == 1
    assert horizon["censored"] == 0
    assert horizon["missing_data"] == 0
    assert horizon["mean_directional_close_return_bps"] == pytest.approx(500.0)
    assert horizon["mean_favorable_excursion_bps"] == pytest.approx(600.0)
    assert horizon["mean_adverse_excursion_bps"] == pytest.approx(100.0)
    evidence_classes = bucket["by_evidence_class"]
    assert evidence_classes["eligible_signal"]["horizons"]["5"]["resolved"] == 1
    assert evidence_classes["readiness_annotation"]["horizons"]["5"]["resolved"] == 0
    metric_diagnostics = bucket["metric_diagnostics"]
    assert metric_diagnostics["coverage"]["complete"] is True
    adx = metric_diagnostics["metrics"]["adx"]
    assert adx["kind"] == "numeric"
    assert adx["horizons"]["5"]["positive_directional"] == {
        "count": 1,
        "mean_metric": 18.0,
        "mean_directional_return_bps": pytest.approx(500.0),
    }
    assert outcomes["coverage"]["metric_telemetry_complete"] is True
    assert (
        "metric-conditioned outcomes are descriptive and do not select thresholds"
        in outcomes["limitations"]
    )


def test_short_direction_inverts_return_and_excursion_signs() -> None:
    """Short diagnostics treat falling prices as favorable without fake PnL."""
    rows = _cohort_rows()
    routing = _payload(rows[1])
    evaluation = _first_object(routing, "evaluations")
    evaluation["side"] = "short"
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["side"] = "short"
    candles = _nested_list(_payload(rows[2]), "bars", "BTC")
    for offset, candle_value in enumerate(candles):
        assert isinstance(candle_value, dict)
        candle_value.update(
            {
                "open": 100.0 - offset,
                "high": 101.0 - offset,
                "low": 98.0 - offset,
                "close": 99.0 - offset,
            }
        )

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    horizon = report["signal_outcomes"]["by_provider_symbol"][f"{_STRATEGY}|BTC"][
        "horizons"
    ]["5"]
    assert horizon["mean_directional_close_return_bps"] == pytest.approx(500.0)
    assert horizon["mean_favorable_excursion_bps"] == pytest.approx(600.0)
    assert horizon["mean_adverse_excursion_bps"] == pytest.approx(100.0)


def test_preactivation_readiness_seed_is_excluded_from_forward_evidence() -> None:
    """Startup history may populate the TUI but cannot become live evidence."""
    rows = _cohort_rows()
    evaluation = _first_object(_payload(rows[1]), "evaluations")
    evaluation["decision_time_ms"] = _DECISION_MS - 60_000

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    outcomes = report["signal_outcomes"]
    assert outcomes["evaluations"] == 0
    assert outcomes["eligible_evaluations"] == 0
    assert outcomes["preactivation_annotations_excluded"] == 1
    assert outcomes["by_provider_symbol"] == {}


def test_readiness_seed_at_activation_boundary_is_also_excluded() -> None:
    """The no-retro-entry boundary is exclusive for forward diagnostics too."""
    rows = _cohort_rows()
    rows[0]["observed_at_utc"] = datetime.fromtimestamp(
        _DECISION_MS / 1_000, timezone.utc
    ).isoformat()

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    outcomes = report["signal_outcomes"]
    assert outcomes["evaluations"] == 0
    assert outcomes["preactivation_annotations_excluded"] == 1


def test_overlapping_paths_report_a_non_overlapping_effective_count() -> None:
    """Dense decisions cannot masquerade as independent forward observations."""
    rows = _cohort_rows()
    routing = _payload(rows[1])
    evaluations = routing["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    second = deepcopy(evaluations[0])
    second["decision_time_ms"] = _DECISION_MS + 60_000
    second["reference_price"] = 101.0
    evaluations.append(second)
    rows[1]["observed_at_utc"] = datetime.fromtimestamp(
        (_DECISION_MS + 60_000) / 1_000, timezone.utc
    ).isoformat()
    bars_by_symbol = _payload(rows[2])["bars"]
    assert isinstance(bars_by_symbol, dict)
    bars = bars_by_symbol["BTC"]
    assert isinstance(bars, list)
    bars.append(
        {
            "timestamp_ms": _DECISION_MS + 5 * 60_000,
            "open": 105.0,
            "high": 107.0,
            "low": 104.0,
            "close": 106.0,
            "volume": 10.0,
        }
    )

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    horizon = report["signal_outcomes"]["by_provider_symbol"][f"{_STRATEGY}|BTC"][
        "horizons"
    ]["5"]
    assert horizon["resolved"] == 2
    assert horizon["non_overlapping_resolved"] == 1


def test_portfolio_opportunity_dedup_measures_dense_decision_cadence() -> None:
    """Repeated one-minute annotations disclose near-continuous coverage."""
    rows = _cohort_rows()
    evaluations = _payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    first = evaluations[0]
    first.update({"eligible": False, "side": None, "decision_action": "hold"})
    readiness = first["readiness"]
    assert isinstance(readiness, dict)
    readiness["blockers"] = ["awaiting_breakout"]
    second = deepcopy(first)
    second.update(
        {
            "decision_time_ms": _DECISION_MS + 60_000,
            "reference_price": 101.0,
        }
    )
    evaluations.append(second)

    outcomes = build_provider_forward_diagnostics(rows)

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    attribution = dedup["by_attribution"]
    assert isinstance(attribution, list) and len(attribution) == 1
    assert attribution[0]["decision_cadence"] == {
        "coverage_rate": 1.0,
        "decision_minutes": 2,
        "episode_count": 1,
        "maximum_episode_duration_minutes": 2,
        "maximum_interval_minutes": 1.0,
        "median_episode_duration_minutes": 2.0,
        "median_interval_minutes": 1.0,
        "minute_boundaries_in_span": 2,
        "single_minute_episodes": 0,
    }


def test_portfolio_opportunity_dedup_splits_cadence_after_a_missing_minute() -> None:
    """A discontinuity starts a distinct actionable annotation episode."""
    rows = _cohort_rows()
    evaluations = _payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    first = evaluations[0]
    first.update({"eligible": False, "side": None, "decision_action": "hold"})
    readiness = first["readiness"]
    assert isinstance(readiness, dict)
    readiness["blockers"] = ["awaiting_breakout"]
    for offset in (1, 3):
        later = deepcopy(first)
        later.update(
            {
                "decision_time_ms": _DECISION_MS + offset * 60_000,
                "reference_price": 100.0 + offset,
            }
        )
        evaluations.append(later)

    outcomes = build_provider_forward_diagnostics(rows)

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    attribution = dedup["by_attribution"]
    assert isinstance(attribution, list) and len(attribution) == 1
    assert attribution[0]["decision_cadence"] == {
        "coverage_rate": 0.75,
        "decision_minutes": 3,
        "episode_count": 2,
        "maximum_episode_duration_minutes": 2,
        "maximum_interval_minutes": 2.0,
        "median_episode_duration_minutes": 1.5,
        "median_interval_minutes": 1.5,
        "minute_boundaries_in_span": 4,
        "single_minute_episodes": 1,
    }


def test_portfolio_opportunity_dedup_surfaces_opposing_direction_hypotheses() -> None:
    """Opposing sides share a market event but must not be merged as duplicates."""
    rows = _cohort_rows()
    evaluations = _payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    first = evaluations[0]
    first.update({"eligible": False, "side": None, "decision_action": "hold"})
    first_readiness = first["readiness"]
    assert isinstance(first_readiness, dict)
    first_readiness["blockers"] = ["awaiting_long_breakout"]
    second = deepcopy(first)
    second["strategy_id"] = "opposing_provider"
    second_readiness = second["readiness"]
    assert isinstance(second_readiness, dict)
    second_readiness.update({"side": "short", "blockers": ["awaiting_short_breakout"]})
    evaluations.append(second)

    outcomes = build_provider_forward_diagnostics(rows)

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    assert dedup["provider_observations"] == 2
    assert dedup["unique_directional_paths"] == 2
    assert dedup["duplicate_provider_observations_removed"] == 0
    assert dedup["direction_competition_groups"] == 1


def test_portfolio_opportunity_dedup_excludes_reference_price_conflicts() -> None:
    """Conflicting causal prices cannot be silently resolved using one provider."""
    rows = _cohort_rows()
    evaluations = _payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    first = evaluations[0]
    first.update({"eligible": False, "side": None, "decision_action": "hold"})
    first_readiness = first["readiness"]
    assert isinstance(first_readiness, dict)
    first_readiness["blockers"] = ["awaiting_breakout"]
    second = deepcopy(first)
    second.update({"strategy_id": "stale_reference_provider", "reference_price": 99.0})
    evaluations.append(second)

    outcomes = build_provider_forward_diagnostics(rows)

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    assert dedup["reference_price_conflict_groups"] == 1
    horizon = dedup["horizons"]["5"]
    assert horizon["reference_price_conflicts"] == 1
    assert horizon["resolved"] == 0
    assert horizon["opportunity_capture"]["resolved"] == 0


def test_readiness_annotation_outcomes_remain_separate_and_blocker_attributed() -> None:
    """Near-setups may explain blockers but cannot be pooled with fired signals."""
    rows = _cohort_rows()
    evaluation = _first_object(_payload(rows[1]), "evaluations")
    evaluation.update({"eligible": False, "side": None, "reason": "no_trigger"})
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness.update(
        {
            "conditions_met": 5,
            "readiness_fraction": 5 / 6,
            "blockers": ["squeeze_not_armed"],
        }
    )

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    bucket = report["signal_outcomes"]["by_provider_symbol"][f"{_STRATEGY}|BTC"]
    assert bucket["eligible_evaluations"] == 0
    assert bucket["readiness_annotations"] == 1
    assert (
        bucket["by_evidence_class"]["eligible_signal"]["horizons"]["5"]["resolved"] == 0
    )
    readiness_horizon = bucket["by_evidence_class"]["readiness_annotation"]["horizons"][
        "5"
    ]
    assert readiness_horizon["mean_directional_close_return_bps"] == pytest.approx(
        500.0
    )
    blocker_horizon = bucket["by_blocker"]["squeeze_not_armed"]["horizons"]["5"]
    assert blocker_horizon["resolved"] == 1


def test_one_blocker_near_miss_quantifies_cost_clearing_path_without_fake_fill() -> (
    None
):
    """A causal near miss reports path opportunity without inventing execution."""
    rows = _cohort_rows()
    evaluation = _first_object(_payload(rows[1]), "evaluations")
    evaluation.update({"eligible": False, "side": None, "reason": "no_trigger"})
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness.update(
        {
            "conditions_met": 5,
            "readiness_fraction": 5 / 6,
            "blockers": ["squeeze_not_armed"],
        }
    )

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    outcomes = report["signal_outcomes"]
    assert outcomes["opportunity_hurdles_bps"] == {
        "estimated_round_trip_friction": 13.0,
        "robust_gross_move": 26.0,
    }
    near_miss = outcomes["by_provider_symbol"][f"{_STRATEGY}|BTC"][
        "one_blocker_near_misses"
    ]
    assert near_miss["evaluations"] == 1
    horizon = near_miss["by_blocker"]["squeeze_not_armed"]["horizons"]["5"]
    capture = horizon["opportunity_capture"]
    assert capture["cost_clearing_mfe_count"] == 1
    assert capture["robust_mfe_count"] == 1
    assert capture["cost_clearing_close_count"] == 1
    assert capture["reversed_after_cost_clear_count"] == 0
    assert capture["mean_close_after_estimated_friction_bps"] == pytest.approx(487.0)
    assert outcomes["contract"]["fills_assumed"] is False
    assert outcomes["contract"]["pnl_claimed"] is False
    orderbook = report["orderbook_opportunity"]["by_provider_symbol"]
    context = orderbook[f"{_STRATEGY}|BTC"]["by_blocker"]["squeeze_not_armed"][
        "by_side"
    ]["long"]["horizons"]["5"]
    assert context["aligned"]["paths"] == 1


def test_ineligible_direction_conflict_is_excluded_and_reported() -> None:
    """Contradictory hold telemetry cannot silently choose a path direction."""
    rows = _cohort_rows()
    evaluation = _first_object(_payload(rows[1]), "evaluations")
    evaluation.update({"eligible": False, "decision_action": "hold", "side": "long"})
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["side"] = "short"

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    outcomes = report["signal_outcomes"]
    assert outcomes["directional_evaluations"] == 0
    assert outcomes["coverage"]["direction_conflicts"] == 1
    assert outcomes["coverage"]["complete"] is False
    bucket = outcomes["by_provider_symbol"][f"{_STRATEGY}|BTC"]
    assert bucket["no_direction"] == 1
    assert bucket["horizons"]["5"]["resolved"] == 0
    assert report["coverage"]["technical_gaps"] == [
        "provider_direction_telemetry_conflict"
    ]


def test_eligible_direction_conflict_remains_a_hard_failure() -> None:
    """An executable signal with contradictory sides remains structurally invalid."""
    rows = _cohort_rows()
    evaluation = _first_object(_payload(rows[1]), "evaluations")
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["side"] = "short"

    with pytest.raises(ValueError, match="directions disagree"):
        audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)


def test_missing_future_candle_is_a_technical_coverage_gap() -> None:
    """A hole inside an elapsed horizon is missing data, not poor signal evidence."""
    rows = _cohort_rows()
    bars = _nested_list(_payload(rows[2]), "bars", "BTC")
    del bars[2]

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    horizon = report["signal_outcomes"]["by_provider_symbol"][f"{_STRATEGY}|BTC"][
        "horizons"
    ]["5"]
    assert horizon["resolved"] == 0
    assert horizon["missing_data"] == 1
    assert report["coverage"] == {
        "complete": False,
        "technical_gaps": ["signal_outcome_market_data_missing"],
    }


def test_later_missing_metrics_are_a_technical_coverage_gap() -> None:
    """A decision remains observable when exact metric telemetry disappears."""
    rows = _cohort_rows()
    evaluations = _payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    second = deepcopy(evaluations[0])
    second["decision_time_ms"] = _DECISION_MS + 60_000
    second["reference_price"] = 101.0
    readiness = second["readiness"]
    assert isinstance(readiness, dict)
    readiness["metrics"] = {}
    evaluations.append(second)
    rows[1]["observed_at_utc"] = datetime.fromtimestamp(
        (_DECISION_MS + 60_000) / 1_000, timezone.utc
    ).isoformat()
    bars = _nested_list(_payload(rows[2]), "bars", "BTC")
    bars.append(
        {
            "timestamp_ms": _DECISION_MS + 5 * 60_000,
            "open": 105.0,
            "high": 107.0,
            "low": 104.0,
            "close": 106.0,
            "volume": 10.0,
        }
    )

    report = audit_multi_asset_live_run(rows, {"BTC": _asset_rows()}, run_id=_RUN_ID)

    outcomes = report["signal_outcomes"]
    assert outcomes["evaluations"] == 2
    assert outcomes["coverage"]["metric_telemetry_complete"] is False
    metric_coverage = outcomes["by_provider_symbol"][f"{_STRATEGY}|BTC"][
        "metric_diagnostics"
    ]["coverage"]
    assert metric_coverage == {
        "complete": False,
        "evaluations_with_metrics": 1,
        "evaluations_without_metrics": 1,
        "metric_value_gaps": 1,
    }
    assert report["coverage"] == {
        "complete": False,
        "technical_gaps": ["provider_metric_telemetry_missing"],
    }
