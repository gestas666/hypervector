"""Availability-causal forward-path regressions for cohort diagnostics."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from cohort_signal_outcomes_fixtures import (
    DECISION_MS,
    RUN_ID,
    STRATEGY,
    asset_rows,
    bars,
    cohort_rows,
    first_object,
    nested_list,
    payload,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run


def _late_one_blocker_rows() -> list[dict[str, object]]:
    rows = cohort_rows()
    evaluation = first_object(payload(rows[1]), "evaluations")
    evaluation.update({"eligible": False, "decision_action": "hold", "side": None})
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["blockers"] = ["awaiting_breakout"]
    rows[1]["observed_at_utc"] = datetime.fromtimestamp(
        (DECISION_MS + 5_000) / 1_000, timezone.utc
    ).isoformat()
    future = nested_list(payload(rows[2]), "bars", "BTC")
    first = future[0]
    assert isinstance(first, dict)
    first["high"] = 1_000.0
    future.append(
        deepcopy(bars()[-1])
        | {
            "timestamp_ms": DECISION_MS + 300_000,
            "open": 105.0,
            "high": 107.0,
            "low": 104.0,
            "close": 106.0,
        }
    )
    return rows


def test_late_availability_excludes_pre_available_candle_everywhere() -> None:
    """No diagnostic may consume a candle that began before signal availability."""
    report = audit_multi_asset_live_run(
        _late_one_blocker_rows(), {"BTC": asset_rows()}, run_id=RUN_ID
    )
    outcomes = report["signal_outcomes"]
    route = outcomes["by_provider_symbol"][f"{STRATEGY}|BTC"]
    path = route["one_blocker_near_misses"]["by_blocker"]["awaiting_breakout"]
    capture = path["horizons"]["5"]["independent_opportunity_capture"]
    portfolio = outcomes["portfolio_opportunity_dedup"]["horizons"]["5"]
    orderbook = report["orderbook_opportunity"]["by_provider_symbol"]
    book_path = orderbook[f"{STRATEGY}|BTC"]["by_blocker"]["awaiting_breakout"]
    book_capture = book_path["by_side"]["long"]["horizons"]["5"]["all"]

    assert outcomes["contract"]["path_start_policy"] == (
        "first_full_minute_at_or_after_candidate_availability"
    )
    assert path["horizons"]["5"]["mean_favorable_excursion_bps"] == pytest.approx(700.0)
    assert capture["mean_close_after_estimated_friction_bps"] == pytest.approx(587.0)
    assert portfolio["independent_opportunity_capture"][
        "mean_close_after_estimated_friction_bps"
    ] == pytest.approx(587.0)
    assert book_capture["opportunity_capture"][
        "mean_close_after_estimated_friction_bps"
    ] == pytest.approx(587.0)


def test_boundary_availability_retains_the_decision_minute() -> None:
    """A candidate available exactly on the boundary may use that full minute."""
    report = audit_multi_asset_live_run(
        cohort_rows(), {"BTC": asset_rows()}, run_id=RUN_ID
    )
    route = report["signal_outcomes"]["by_provider_symbol"][f"{STRATEGY}|BTC"]

    assert route["horizons"]["5"]["mean_directional_close_return_bps"] == pytest.approx(
        500.0
    )
