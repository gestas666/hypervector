"""Executable replay for causal, exact-one-blocker cohort opportunities."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_one_blocker_execution_feasibility import (
    OneBlockerExecutionContract,
    build_one_blocker_execution_feasibility,
)

_DECISION_MS = 1_800_000_000_000


def test_long_replay_waits_for_publication_and_honors_first_stop_proxy() -> None:
    """A hypothetical long exits at the first adverse BBO stop crossing."""
    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": _books()},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["selected_non_overlapping"] == 1
    assert report["coverage"]["resolved_executions"] == 1
    trade = report["executions"][0]
    assert trade["entry_time_ms"] == _DECISION_MS + 3_000
    assert trade["entry_price"] == 100.02
    assert trade["exit_time_ms"] == _DECISION_MS + 120_000
    assert trade["exit_price"] == 99.0
    assert trade["exit_reason"] == "stop_proxy"
    assert trade["funding_bps"] == pytest.approx(0.0)
    assert trade["net_return_bps"] < 0.0
    assert trade["crossed_stop_proxy"] is True
    assert report["by_side"]["long"]["resolved"] == 1
    assert report["contract"]["live_pnl_claimed"] is False


def test_stop_resolves_before_the_fixed_horizon_book_exists() -> None:
    """An observed stop crossing must not wait for a future horizon snapshot."""
    books = _books()[:3]

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["exit_pending"] == 0
    assert report["coverage"]["exit_missing"] == 0
    assert report["coverage"]["resolved_executions"] == 1
    assert report["attempts"][0]["status"] == "resolved"
    assert report["executions"][0]["exit_reason"] == "stop_proxy"
    assert report["executions"][0]["exit_time_ms"] == _DECISION_MS + 120_000


def test_target_resolves_before_a_later_stop_and_fixed_horizon() -> None:
    """An executable target touch exits before subsequent adverse movement."""
    books = _books()
    books.insert(2, _book_row(_DECISION_MS + 60_000, 100.25, 100.27, 0.4))

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=replace(_contract(), target_proxy_bps=20.0),
    )

    trade = report["executions"][0]
    assert trade["exit_time_ms"] == _DECISION_MS + 60_000
    assert trade["exit_price"] == 100.25
    assert trade["exit_reason"] == "target_proxy"
    assert trade["crossed_stop_proxy"] is False
    assert trade["net_return_bps"] > 10.0
    assert report["by_side"]["long"]["target_proxy_crosses"] == 1


def test_target_contract_is_explicit_in_report_payload() -> None:
    """A target-enabled replay must disclose its immutable exit mechanics."""
    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": _books()},
        _funding_rows(0.00001),
        contract=replace(_contract(), target_proxy_bps=20.0),
    )

    assert report["contract"]["target_proxy_bps"] == 20.0
    assert report["contract"]["exit_rule"] == (
        "first_recorded_target_or_stop_bbo_otherwise_fixed_horizon"
    )


@pytest.mark.parametrize("target_bps", [0.0, -1.0, float("nan"), float("inf")])
def test_target_contract_rejects_nonpositive_or_nonfinite_values(
    target_bps: float,
) -> None:
    """A configured target must be positive and finite."""
    with pytest.raises(ValueError, match="target proxy must be positive and finite"):
        replace(_contract(), target_proxy_bps=target_bps)


def test_future_horizon_exposes_pending_path_without_fake_resolution() -> None:
    """An open replay path reports interim economics but remains unresolved."""
    books = _books()[:2] + [_book_row(_DECISION_MS + 120_000, 100.48, 100.50, 0.4)]

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["exit_pending"] == 1
    assert report["coverage"]["exit_missing"] == 0
    assert report["coverage"]["resolved_executions"] == 0
    assert report["executions"] == []
    attempt = report["attempts"][0]
    assert attempt["status"] == "exit_pending"
    assert attempt["entry_time_ms"] == _DECISION_MS + 3_000
    assert attempt["entry_price"] == 100.02
    assert attempt["deadline_time_ms"] == _DECISION_MS + 303_000
    assert attempt["latest_book_time_ms"] == _DECISION_MS + 120_000
    assert attempt["remaining_ms"] == 183_000
    assert attempt["current_gross_return_bps"] > 40.0
    assert attempt["current_estimated_net_return_bps"] > 30.0
    assert attempt["mfe_bps"] == pytest.approx(attempt["current_gross_return_bps"])
    assert attempt["mae_bps"] < 0.0
    assert attempt["current_exit_top_level_capacity"] is True


def test_short_replay_inverts_bbo_and_funding_direction() -> None:
    """A short enters at bid, exits at ask, and receives positive funding."""
    books = _books()
    for row in books:
        payload = row["payload"]
        assert isinstance(payload, dict)
        payload["opi"] = -0.4
    exit_payload = books[-1]["payload"]
    assert isinstance(exit_payload, dict)
    exit_payload["bids"] = [{"price": 98.98, "size": 1.0}]
    exit_payload["asks"] = [{"price": 99.0, "size": 1.0}]

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("short"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    trade = report["executions"][0]
    assert trade["entry_price"] == 100.0
    assert trade["exit_price"] == 99.0
    assert trade["funding_bps"] == pytest.approx(0.1)
    assert trade["net_return_bps"] > 90.0
    assert report["by_side"]["short"]["resolved"] == 1


def test_top_level_capacity_failure_is_retained_without_fake_fill() -> None:
    """Insufficient visible BBO size is a failed attempt, not a filled trade."""
    books = _books()
    entry_payload = books[1]["payload"]
    assert isinstance(entry_payload, dict)
    entry_payload["asks"] = [{"price": 100.02, "size": 0.01}]

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["selected_non_overlapping"] == 1
    assert report["coverage"]["entry_capacity_failures"] == 1
    assert report["coverage"]["resolved_executions"] == 0
    assert report["executions"] == []


def test_candidate_before_actual_exit_cannot_create_a_second_position() -> None:
    """Entry latency cannot let nominally spaced signals overlap one position."""
    rows = _cohort_rows("long")
    for offset in (300_000, 360_000):
        evaluation = _evaluation("long", _DECISION_MS + offset)
        rows.append(
            _row(
                "intent_routing",
                {"evaluations": [evaluation]},
                _DECISION_MS + offset + 2_000,
            )
        )
    books = _books()
    intermediate = books[2]["payload"]
    assert isinstance(intermediate, dict)
    intermediate["bids"] = [{"price": 100.0, "size": 1.0}]
    intermediate["asks"] = [{"price": 100.02, "size": 1.0}]
    books.extend(
        [
            _book_row(_DECISION_MS + 301_000, 100.8, 100.82, 0.4),
            _book_row(_DECISION_MS + 361_000, 101.0, 101.02, 0.4),
            _book_row(_DECISION_MS + 363_000, 101.0, 101.02, 0.4),
            _book_row(_DECISION_MS + 663_000, 101.5, 101.52, 0.4),
        ]
    )

    report = build_one_blocker_execution_feasibility(
        rows,
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["selected_non_overlapping"] == 2
    assert [row["decision_time_ms"] for row in report["executions"]] == [
        _DECISION_MS,
        _DECISION_MS + 360_000,
    ]


def test_minimum_entry_spacing_can_extend_beyond_the_fixed_hold() -> None:
    """A prospective re-entry buffer is distinct from the position horizon."""
    rows = _cohort_rows("long")
    for offset in (360_000, 420_000):
        rows.append(
            _row(
                "intent_routing",
                {"evaluations": [_evaluation("long", _DECISION_MS + offset)]},
                _DECISION_MS + offset + 2_000,
            )
        )
    books = _books() + [
        _book_row(_DECISION_MS + 361_000, 101.0, 101.02, 0.4),
        _book_row(_DECISION_MS + 421_000, 101.1, 101.12, 0.4),
        _book_row(_DECISION_MS + 423_000, 101.1, 101.12, 0.4),
        _book_row(_DECISION_MS + 723_000, 101.5, 101.52, 0.4),
    ]

    report = build_one_blocker_execution_feasibility(
        rows,
        {"BTC": books},
        _funding_rows(0.00001),
        contract=replace(_contract(), minimum_entry_spacing_minutes=7),
    )

    assert report["contract"]["horizon_minutes"] == 5
    assert report["contract"]["minimum_entry_spacing_minutes"] == 7
    assert [row["decision_time_ms"] for row in report["executions"]] == [
        _DECISION_MS,
        _DECISION_MS + 420_000,
    ]


def test_opposed_opi_cohort_is_selectable_without_changing_thresholds() -> None:
    """The fixed comparison may select negative directional OPI explicitly."""
    books = _books()
    for row in books:
        values = row["payload"]
        assert isinstance(values, dict)
        values["opi"] = -0.4

    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": books},
        _funding_rows(0.00001),
        contract=replace(_contract(), opi_cohort="opposed"),
    )

    assert report["coverage"]["context_cohort_excluded"] == 0
    assert report["coverage"]["resolved_executions"] == 1
    assert report["executions"][0]["directional_opi"] < 0.0


def test_execution_retains_causal_entry_features_for_future_stratification() -> None:
    """Resolved paths retain only decision-time features from their signal row."""
    rows = _cohort_rows("long")
    routing = rows[1]["payload"]
    assert isinstance(routing, dict)
    evaluations = routing["evaluations"]
    assert isinstance(evaluations, list)
    evaluation = evaluations[0]
    evaluation["primary_regime"] = "RANGE"
    evaluation["state_1m"] = "TRANSITION"
    evaluation["state_5m"] = "TREND_DOWN"
    evaluation["context_15m"] = "TREND_UP"
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["metrics"] = {
        "breakout_volume_ratio": 0.42,
        "directional_return_5m_bps": -8.0,
        "entry_feature_authority": "report_only",
        "unrelated_internal_value": 99.0,
    }

    report = build_one_blocker_execution_feasibility(
        rows,
        {"BTC": _books()},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    expected = {
        "primary_regime": "RANGE",
        "state_1m": "TRANSITION",
        "state_5m": "TREND_DOWN",
        "context_15m": "TREND_UP",
        "breakout_volume_ratio": 0.42,
        "directional_return_5m_bps": -8.0,
        "entry_feature_authority": "report_only",
    }
    assert report["attempts"][0]["entry_features"] == expected
    assert report["executions"][0]["entry_features"] == expected


def test_frozen_cutoff_excludes_predeclared_development_candidates() -> None:
    """A forward contract must not reuse candidates published before its cutoff."""
    report = build_one_blocker_execution_feasibility(
        _cohort_rows("long"),
        {"BTC": _books()},
        _funding_rows(0.00001),
        contract=replace(_contract(), minimum_available_time_ms=_DECISION_MS + 60_000),
    )

    assert report["coverage"]["pre_cutoff_excluded"] == 1
    assert report["coverage"]["exact_candidates"] == 1
    assert report["coverage"]["context_stale"] == 1
    assert report["coverage"]["resolved_executions"] == 0


def test_compatible_runs_share_one_non_overlapping_replay_timeline() -> None:
    """A restart preserves an open observation and its source-run identity."""
    rows = [
        _tag(_row("configuration_identity", {}, _DECISION_MS - 60_000), "run-a"),
        _tag(
            _row(
                "intent_routing",
                {"evaluations": [_evaluation("long", _DECISION_MS)]},
                _DECISION_MS + 2_000,
            ),
            "run-a",
        ),
        _tag(_row("configuration_identity", {}, _DECISION_MS + 60_000), "run-b"),
        _tag(
            _row(
                "intent_routing",
                {"evaluations": [_evaluation("long", _DECISION_MS + 120_000)]},
                _DECISION_MS + 122_000,
            ),
            "run-b",
        ),
        _tag(
            _row(
                "intent_routing",
                {"evaluations": [_evaluation("long", _DECISION_MS + 360_000)]},
                _DECISION_MS + 362_000,
            ),
            "run-b",
        ),
    ]
    books = [
        _book_row(_DECISION_MS + 1_000, 99.98, 100.00, 0.4),
        _book_row(_DECISION_MS + 3_000, 100.00, 100.02, 0.4),
        _book_row(_DECISION_MS + 120_000, 100.08, 100.10, 0.4),
        _book_row(_DECISION_MS + 303_000, 100.18, 100.20, 0.4),
        _book_row(_DECISION_MS + 361_000, 100.18, 100.20, 0.4),
        _book_row(_DECISION_MS + 363_000, 100.20, 100.22, 0.4),
        _book_row(_DECISION_MS + 663_000, 100.30, 100.32, 0.4),
    ]

    report = build_one_blocker_execution_feasibility(
        rows,
        {"BTC": books},
        _funding_rows(0.00001),
        contract=_contract(),
    )

    assert report["coverage"]["exact_candidates"] == 3
    assert report["coverage"]["selected_non_overlapping"] == 2
    assert [row["source_run_id"] for row in report["executions"]] == [
        "run-a",
        "run-b",
    ]
    assert report["executions"][0]["exit_time_ms"] == _DECISION_MS + 303_000


def _contract() -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id="range_onset_bidirectional_v1",
        symbol="BTC",
        blocker="awaiting_hourly_sma_cross",
        horizon_minutes=5,
        maximum_context_age_ms=30_000,
        maximum_entry_delay_ms=30_000,
        maximum_exit_delay_ms=30_000,
        notional_usd=25.0,
        taker_fee_rate=0.000432,
        stop_proxy_bps=60.0,
        opi_cohort="aligned",
    )


def _cohort_rows(side: str) -> list[dict[str, object]]:
    evaluation = _evaluation(side, _DECISION_MS)
    duplicate = _evaluation(side, _DECISION_MS + 60_000)
    return [
        _row("configuration_identity", {}, _DECISION_MS - 60_000),
        _row("intent_routing", {"evaluations": [evaluation]}, _DECISION_MS + 2_000),
        _row(
            "intent_routing",
            {"evaluations": [duplicate]},
            _DECISION_MS + 62_000,
        ),
    ]


def _evaluation(side: str, decision_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "BTC",
        "decision_time_ms": decision_ms,
        "reference_price": 100.0,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": side,
            "blockers": ["awaiting_hourly_sma_cross"],
            "metrics": {},
        },
    }


def _books() -> list[dict[str, object]]:
    points = (
        (_DECISION_MS + 1_000, 99.98, 100.00, 0.4),
        (_DECISION_MS + 3_000, 100.00, 100.02, 0.4),
        (_DECISION_MS + 120_000, 99.00, 99.02, 0.4),
        (_DECISION_MS + 303_000, 101.02, 101.04, 0.4),
    )
    return [
        _book_row(observed_ms, bid, ask, opi) for observed_ms, bid, ask, opi in points
    ]


def _book_row(
    observed_ms: int, bid: float, ask: float, opi: float
) -> dict[str, object]:
    return _row(
        "book_observation",
        {
            "recv_ts_ms": observed_ms,
            "exchange_ts_ms": observed_ms - 50,
            "opi": opi,
            "spread_bps": 2.0,
            "bid_depth_ratio": 1.5,
            "bids": [{"price": bid, "size": 1.0}],
            "asks": [{"price": ask, "size": 1.0}],
        },
        observed_ms,
    )


def _funding_rows(rate: float) -> list[dict[str, object]]:
    return [
        {
            "event_ts_ms": _DECISION_MS + 180_000,
            "funding_rate": rate,
            "source": "hl_funding_history",
        }
    ]


def _row(
    event_type: str,
    payload: dict[str, object],
    observed_ms: int,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "payload": payload,
    }


def _tag(row: dict[str, object], source_run_id: str) -> dict[str, object]:
    return row | {"run_id": source_run_id}
