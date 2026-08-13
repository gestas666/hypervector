"""Cross-portfolio executable opportunity matrix tests."""

from __future__ import annotations

from datetime import datetime, timezone

from hypervector.research.cohort_execution_opportunity_matrix import (
    ProviderReplaySettings,
    build_execution_opportunity_matrix,
)

_DECISION_MS = 1_800_000_000_000


def test_matrix_retains_aligned_opposed_and_all_cohorts_without_pooling() -> None:
    """A fixed blocker hypothesis exposes each OPI cohort and both-side evidence."""
    report = build_execution_opportunity_matrix(
        _cohort_rows(),
        {"BTC": _book_rows()},
        {"BTC": _funding_rows()},
        settings_by_pair={
            ("range_onset_bidirectional_v1", "BTC"): ProviderReplaySettings(
                maximum_entry_delay_ms=60_000,
                notional_usd=25.0,
                stop_proxy_bps=60.0,
            )
        },
        horizon_minutes=5,
        taker_fee_rate=0.000432,
    )

    assert report["contract"]["portfolio_pnl_claimed"] is False
    assert report["hypotheses"] == 1
    assert report["comparisons"] == 3
    by_cohort = {row["opi_cohort"]: row for row in report["results"]}
    assert by_cohort["aligned"]["resolved"] == 1
    assert by_cohort["aligned"]["long"]["wins"] == 1
    assert by_cohort["aligned"]["net_return_excluding_largest_winner_bps"] == 0.0
    assert by_cohort["opposed"]["resolved"] == 0
    assert by_cohort["opposed"]["net_return_excluding_largest_winner_bps"] is None
    assert by_cohort["all"]["resolved"] == 1


def test_matrix_attributes_observe_only_hypotheses_without_replaying_them() -> None:
    """Mixed profiles retain explicit scope without inventing replay settings."""
    rows = _cohort_rows()
    routing = rows[-1]["payload"]
    assert isinstance(routing, dict)
    evaluations = routing["evaluations"]
    assert isinstance(evaluations, list)
    evaluations.append(
        {
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "symbol": "ETH",
            "decision_time_ms": _DECISION_MS,
            "reference_price": 100.0,
            "side": "long",
            "eligible": False,
            "readiness": {
                "side": "long",
                "blockers": ["awaiting_pullback"],
                "metrics": {},
            },
        }
    )

    report = build_execution_opportunity_matrix(
        rows,
        {"BTC": _book_rows()},
        {"BTC": _funding_rows()},
        settings_by_pair={
            ("range_onset_bidirectional_v1", "BTC"): ProviderReplaySettings(
                maximum_entry_delay_ms=60_000,
                notional_usd=25.0,
                stop_proxy_bps=60.0,
            )
        },
        horizon_minutes=5,
    )

    assert report["hypotheses"] == 1
    assert report["comparisons"] == 3
    assert report["scope"] == {
        "observed_hypotheses": 2,
        "executable_hypotheses": 1,
        "excluded_non_executable_hypotheses": [
            {
                "strategy_id": (
                    "eth_breakout_precompression_pullback_bidirectional_v1"
                ),
                "symbol": "ETH",
                "blocker": "awaiting_pullback",
            }
        ],
    }


def _cohort_rows() -> list[dict[str, object]]:
    evaluation = {
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "BTC",
        "decision_time_ms": _DECISION_MS,
        "reference_price": 100.0,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": ["awaiting_hourly_sma_cross"],
            "metrics": {},
        },
    }
    return [
        _row("configuration_identity", {}, _DECISION_MS - 60_000),
        _row("intent_routing", {"evaluations": [evaluation]}, _DECISION_MS + 2_000),
    ]


def _book_rows() -> list[dict[str, object]]:
    points = (
        (_DECISION_MS + 1_000, 99.98, 100.0),
        (_DECISION_MS + 3_000, 100.0, 100.02),
        (_DECISION_MS + 303_000, 101.0, 101.02),
    )
    return [
        _row(
            "book_observation",
            {
                "recv_ts_ms": timestamp_ms,
                "exchange_ts_ms": timestamp_ms - 50,
                "opi": 0.4,
                "bids": [{"price": bid, "size": 1.0}],
                "asks": [{"price": ask, "size": 1.0}],
            },
            timestamp_ms,
        )
        for timestamp_ms, bid, ask in points
    ]


def _funding_rows() -> list[dict[str, object]]:
    return [
        {
            "event_ts_ms": _DECISION_MS + 180_000,
            "funding_rate": 0.00001,
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
