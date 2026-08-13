"""Tests for exact visible-depth tracking of eligible cohort signals."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_eligible_exact_depth_forward import (
    build_eligible_exact_depth_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)

_RUN = "observer-v49"


def _cohort() -> list[dict[str, object]]:
    return [
        {
            "event_type": "configuration_identity",
            "run_id": _RUN,
            "observed_at_utc": "1970-01-01T00:00:00+00:00",
            "payload": {"profile_fingerprint": "profile"},
        },
        {
            "event_type": "intent_routing",
            "run_id": _RUN,
            "observed_at_utc": "1970-01-01T00:01:01+00:00",
            "payload": {
                "evaluations": [
                    {
                        "strategy_id": "range_onset_bidirectional_v1",
                        "symbol": "SOL",
                        "decision_time_ms": 60_000,
                        "reference_price": 100.0,
                        "eligible": True,
                        "side": "short",
                        "readiness": {"side": "short", "blockers": [], "metrics": {}},
                    }
                ]
            },
        },
    ]


def _policy() -> dict[str, object]:
    return {
        "mode": "cohort_config_bound_eligible_policy_forward_report",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "source_strategy_id": "range_onset_bidirectional_v1",
            "candidate_strategy_id": "range_onset_sol_v49_config_bound_forward_v1",
            "symbol": "SOL",
            "source_run_id": _RUN,
            "profile_fingerprint": "profile",
            "stop_bps": 80.0,
            "maximum_hold_minutes": 2,
            "notional_usd": 1_000.0,
        },
    }


def _book(
    time_ms: int, bid: float, ask: float, size: float = 100.0
) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "run_id": _RUN,
        "observed_at_utc": "1970-01-01T00:02:00+00:00",
        "payload": {
            "symbol": "SOL",
            "recv_ts_ms": time_ms,
            "exchange_ts_ms": time_ms - 1,
            "bids": [{"price": bid, "size": size}],
            "asks": [{"price": ask, "size": size}],
        },
    }


def _funding(end_ms: int) -> EligiblePolicyFundingEvidence:
    return EligiblePolicyFundingEvidence(
        symbol="SOL",
        requested_start_ms=0,
        requested_end_ms=end_ms,
        events=(),
    )


def test_pending_short_uses_first_post_publication_depth_and_current_exit() -> None:
    books = [_book(62_000, 99.9, 100.1), _book(120_000, 99.0, 99.2)]

    report = build_eligible_exact_depth_forward_report(
        _cohort(),
        books,
        policy_report=_policy(),
        funding_evidence=_funding(120_000),
        taker_fee_rate=0.000432,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
    )

    attempt = report["latest_attempts"][0]
    assert attempt["status"] == "exit_pending"
    assert attempt["entry_time_ms"] == 62_000
    assert attempt["entry_price"] == pytest.approx(99.9)
    assert attempt["current_exit_price"] == pytest.approx(99.2)
    assert attempt["current_gross_return_bps"] == pytest.approx(
        (99.9 / 99.2 - 1.0) * 10_000.0
    )
    assert attempt["current_funding_bps"] == 0.0
    assert attempt["current_net_return_bps"] < attempt["current_gross_return_bps"]
    assert report["contract"]["execution_authority"] == "none"


def test_pending_path_uses_books_from_a_compatible_observer_restart() -> None:
    """Restarted collection must advance rather than freeze an open lifecycle."""
    continuation = "observer-v49-restart"
    cohort = _cohort()
    identity = dict(cohort[0], run_id=continuation)
    policy = _policy()
    policy["contract"]["compatible_run_ids"] = [_RUN, continuation]
    later = _book(120_000, 99.0, 99.2)
    later["run_id"] = continuation

    report = build_eligible_exact_depth_forward_report(
        [*cohort, identity],
        [_book(62_000, 99.9, 100.1), later],
        policy_report=policy,
        funding_evidence=_funding(120_000),
        taker_fee_rate=0.000432,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
    )

    attempt = report["latest_attempts"][0]
    assert attempt["status"] == "exit_pending"
    assert attempt["current_exit_time_ms"] == 120_000
    assert report["contract"]["compatible_run_ids"] == [_RUN, continuation]


def test_first_adverse_bbo_cross_resolves_at_visible_depth_stop_exit() -> None:
    books = [
        _book(62_000, 99.9, 100.1),
        _book(90_000, 100.4, 100.6),
        _book(100_000, 100.7, 100.8),
    ]

    report = build_eligible_exact_depth_forward_report(
        _cohort(),
        books,
        policy_report=_policy(),
        funding_evidence=_funding(100_000),
        taker_fee_rate=0.000432,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
    )

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "protective_stop"
    assert execution["exit_time_ms"] == 100_000
    assert execution["exit_price"] == pytest.approx(100.8)
    assert execution["net_return_bps"] < -80.0


def test_insufficient_entry_depth_is_explicit_not_success_shaped() -> None:
    books = [_book(62_000, 99.9, 100.1, size=1.0)]

    report = build_eligible_exact_depth_forward_report(
        _cohort(),
        books,
        policy_report=_policy(),
        funding_evidence=_funding(62_000),
        taker_fee_rate=0.000432,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
    )

    assert report["latest_attempts"][0]["status"] == "entry_capacity_insufficient"
    assert report["latest_executions"] == []
