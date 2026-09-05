"""Causal REST-to-WebSocket HIP-3 mark response-lag tests."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_mark_response_lag import (
    Hip3MarkResponseLagSpec,
    build_hip3_mark_response_lag,
)


def test_latest_causal_context_match_reports_receipt_lag() -> None:
    """A REST response matching the latest prior WebSocket row is explicit."""
    rows = (
        _row("ws", 1_000, 100.0, 101.0, 5.0),
        _row("rest", 1_600, 100.0, 101.0, 5.0),
    )

    report = build_hip3_mark_response_lag(
        rows, Hip3MarkResponseLagSpec("xyz:SP500", minimum_rest_rows=1)
    )

    assert report["status"] == "resolved"
    assert report["latest_context_match_rows"] == 1
    assert report["stale_context_rows"] == 0
    assert report["maximum_matching_context_lag_ms"] == 600.0
    assert report["disposition"] == "no_mismatch_observed_not_source_promotion"
    assert report["execution_authority"] == "none"


def test_rest_response_matching_older_context_is_classified_stale() -> None:
    """A later differing WebSocket update falsifies REST receipt-time exactness."""
    rows = (
        _row("ws", 1_000, 100.0, 101.0, 5.0),
        _row("ws", 1_900, 101.0, 102.0, 6.0),
        _row("rest", 2_000, 100.0, 101.0, 5.0),
    )

    report = build_hip3_mark_response_lag(
        rows, Hip3MarkResponseLagSpec("xyz:SP500", minimum_rest_rows=1)
    )

    assert report["stale_context_rows"] == 1
    assert report["latest_context_match_rows"] == 0
    assert report["maximum_matching_context_lag_ms"] == 1_000.0
    assert report["maximum_latest_websocket_age_ms"] == 100.0
    assert report["maximum_mark_difference_to_latest_websocket_bps"] > 99.0
    assert report["disposition"] == "rest_receipt_cannot_certify_exact_mark_time"
    record = report["records"][0]
    assert record["matching_prior_websocket_received_ts_ns"] == 1_000_000_000
    assert record["latest_websocket_received_ts_ns"] == 1_900_000_000


def test_future_only_context_match_remains_causally_unresolved() -> None:
    """A WebSocket row received after REST cannot validate a prior REST receipt."""
    rows = (
        _row("ws", 1_000, 101.0, 102.0, 6.0),
        _row("rest", 2_000, 100.0, 101.0, 5.0),
        _row("ws", 2_100, 100.0, 101.0, 5.0),
    )

    report = build_hip3_mark_response_lag(
        rows, Hip3MarkResponseLagSpec("xyz:SP500", minimum_rest_rows=1)
    )

    assert report["future_only_context_rows"] == 1
    assert report["records"][0]["matching_future_websocket_received_ts_ns"] == (
        2_100_000_000
    )
    assert report["disposition"] == "rest_receipt_cannot_certify_exact_mark_time"


def test_insufficient_rest_rows_cannot_resolve_lag_distribution() -> None:
    """A predeclared minimum prevents a tiny overlap from looking conclusive."""
    rows = (
        _row("ws", 1_000, 100.0, 101.0, 5.0),
        _row("rest", 1_100, 100.0, 101.0, 5.0),
    )

    report = build_hip3_mark_response_lag(
        rows, Hip3MarkResponseLagSpec("xyz:SP500", minimum_rest_rows=2)
    )

    assert report["status"] == "insufficient_overlap"
    assert report["disposition"] == "collect_more_overlap"


def test_conflicting_same_source_receipt_is_rejected() -> None:
    """Two contexts at one source receipt boundary are not silently deduped."""
    rows = (
        _row("ws", 1_000, 100.0, 101.0, 5.0),
        _row("ws", 1_000, 101.0, 101.0, 5.0),
        _row("rest", 1_100, 100.0, 101.0, 5.0),
    )

    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_hip3_mark_response_lag(
            rows, Hip3MarkResponseLagSpec("xyz:SP500", minimum_rest_rows=1)
        )


def _row(
    source: str,
    received_ms: int,
    mark: float,
    oracle: float,
    open_interest: float,
) -> dict[str, object]:
    identities = {
        "rest": "hyperliquid_info_metaAndAssetCtxs",
        "ws": "hyperliquid_ws_activeAssetCtx",
    }
    return {
        "symbol": "xyz:SP500",
        "received_ts_ns": received_ms * 1_000_000,
        "mark_price": mark,
        "oracle_price": oracle,
        "funding_rate_hourly": 0.0001,
        "open_interest": open_interest,
        "mid_price": mark + 0.01,
        "source": identities[source],
    }
