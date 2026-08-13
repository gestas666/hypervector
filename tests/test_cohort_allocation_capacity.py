"""Visible-depth capacity evidence for the selective HYPE allocation trial."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_allocation_capacity import (
    build_allocation_capacity,
)


def test_measures_both_sides_of_candidate_ioc_without_claiming_fills() -> None:
    """Recent public L2 quantifies capacity but cannot grant execution authority."""
    evidence = build_allocation_capacity(
        [_book(1, top_size=2.0), _book(2, top_size=1.0)],
        run_id="run-1",
        current_notional_usd=25.0,
        candidate_notional_usd=75.0,
    )

    assert evidence["status"] == "observed"
    assert evidence["symbol"] == "HYPE"
    assert evidence["snapshot_count"] == 2
    assert evidence["candidate_notional_usd"] == pytest.approx(75.0)
    assert evidence["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "promotion_gate": False,
    }
    long = evidence["by_side"]["long"]
    short = evidence["by_side"]["short"]
    assert long["complete_rate"] == pytest.approx(1.0)
    assert short["complete_rate"] == pytest.approx(1.0)
    assert long["bbo_fill_rate"] == pytest.approx(0.5)
    assert short["bbo_fill_rate"] == pytest.approx(0.5)
    assert long["maximum_impact_bps"] > 0.0
    assert short["maximum_impact_bps"] > long["maximum_impact_bps"]
    assert long["minimum_bbo_notional_usd"] == pytest.approx(50.01)
    assert short["minimum_bbo_notional_usd"] == pytest.approx(49.99)


def test_uses_only_the_selected_run_and_bounded_latest_window() -> None:
    """Unrelated runs and unbounded history cannot inflate capacity coverage."""
    records = [_book(0, run_id="other", top_size=100.0)]
    records.extend(_book(index, top_size=2.0) for index in range(1, 250))

    evidence = build_allocation_capacity(
        records,
        run_id="run-1",
        current_notional_usd=25.0,
        candidate_notional_usd=75.0,
    )

    assert evidence["snapshot_count"] == 240
    assert evidence["window_start_timestamp_ms"] == 10_000
    assert evidence["window_end_timestamp_ms"] == 249_000


def test_rejects_a_success_shaped_book_without_full_depth() -> None:
    """A book missing one side cannot become favorable capacity evidence."""
    record = _book(1, top_size=2.0)
    record["payload"]["asks"] = []

    with pytest.raises(ValueError, match="asks must contain visible depth"):
        build_allocation_capacity(
            [record],
            run_id="run-1",
            current_notional_usd=25.0,
            candidate_notional_usd=75.0,
        )


def _book(
    index: int,
    *,
    run_id: str = "run-1",
    top_size: float,
) -> dict[str, object]:
    timestamp = index * 1_000
    return {
        "event_type": "book_observation",
        "run_id": run_id,
        "payload": {
            "exchange_ts_ms": timestamp - 5,
            "recv_ts_ms": timestamp,
            "mid_px": 50.0,
            "bids": [
                {"price": 49.99, "size": top_size},
                {"price": 49.98, "size": 5.0},
            ],
            "asks": [
                {"price": 50.01, "size": top_size},
                {"price": 50.02, "size": 5.0},
            ],
        },
    }
