"""Tests for recent live-ledger visible-depth evidence."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_recent_liquidity import (
    build_recent_liquidity_profile,
)


def test_builds_midpoint_relative_round_trip_cost_distribution() -> None:
    """Both sides include spread and consumed depth without claiming fills."""
    profile = build_recent_liquidity_profile(
        [
            _identity("BTC", "profile-btc", "a" * 64),
            _book(1, 100.0),
            _book(2, 100.0),
        ],
        run_id="live-a",
        symbol="BTC",
        profile_id="profile-btc",
        profile_fingerprint="a" * 64,
        notional_usd=750.0,
    )

    assert profile["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "automatic_sizing_change": False,
    }
    assert profile["symbol"] == "BTC"
    assert profile["snapshot_count"] == 2
    assert profile["both_complete_rate"] == pytest.approx(1.0)
    costs = profile["round_trip_visible_cost_bps"]
    assert costs["count"] == 2
    assert costs["p50"] == pytest.approx(20.0)
    assert costs["p90"] == pytest.approx(20.0)
    assert costs["p99"] == pytest.approx(20.0)


def test_uses_only_selected_run_and_bounded_latest_snapshots() -> None:
    """Old runs and observations beyond the explicit bound cannot leak in."""
    rows = [_book(1, 100.0, run_id="old")]
    rows.append(_identity("ETH", "profile-eth", "b" * 64))
    rows.extend(
        _book(index, 100.0, symbol="ETH", fingerprint="b" * 64) for index in range(2, 7)
    )

    profile = build_recent_liquidity_profile(
        rows,
        run_id="live-a",
        symbol="ETH",
        profile_id="profile-eth",
        profile_fingerprint="b" * 64,
        notional_usd=750.0,
        maximum_snapshots=3,
    )

    assert profile["snapshot_count"] == 3
    assert profile["window_start_timestamp_ms"] == 4
    assert profile["window_end_timestamp_ms"] == 6


def test_rejects_duplicate_or_reordered_receive_timestamps() -> None:
    """A non-causal live book sequence fails rather than being sorted silently."""
    with pytest.raises(ValueError, match="unique and increasing"):
        build_recent_liquidity_profile(
            [
                _identity("SOL", "profile-sol", "c" * 64),
                _book(2, 100.0, symbol="SOL", fingerprint="c" * 64),
                _book(1, 100.0, symbol="SOL", fingerprint="c" * 64),
            ],
            run_id="live-a",
            symbol="SOL",
            profile_id="profile-sol",
            profile_fingerprint="c" * 64,
            notional_usd=750.0,
        )


def test_reports_incomplete_visible_depth_without_extrapolation() -> None:
    """An insufficient book lowers completion instead of inventing liquidity."""
    row = _book(1, 100.0, symbol="HYPE", fingerprint="d" * 64)
    row["payload"]["asks"] = [{"price": 100.1, "size": 0.1}]

    profile = build_recent_liquidity_profile(
        [_identity("HYPE", "profile-hype", "d" * 64), row],
        run_id="live-a",
        symbol="HYPE",
        profile_id="profile-hype",
        profile_fingerprint="d" * 64,
        notional_usd=750.0,
    )

    assert profile["buy_complete_rate"] == pytest.approx(0.0)
    assert profile["both_complete_rate"] == pytest.approx(0.0)
    assert profile["round_trip_visible_cost_bps"] == {
        "count": 0,
        "p50": None,
        "p90": None,
        "p99": None,
    }


def test_rejects_wrong_asset_or_profile_identity_before_measuring_depth() -> None:
    """A valid BTC book cannot be relabeled as ETH or another profile."""
    rows = [_identity("BTC", "profile-btc", "a" * 64), _book(1, 100.0)]

    with pytest.raises(ValueError, match="symbol does not match"):
        build_recent_liquidity_profile(
            rows,
            run_id="live-a",
            symbol="ETH",
            profile_id="profile-btc",
            profile_fingerprint="a" * 64,
            notional_usd=750.0,
        )
    with pytest.raises(ValueError, match="profile identity does not match"):
        build_recent_liquidity_profile(
            rows,
            run_id="live-a",
            symbol="BTC",
            profile_id="profile-eth",
            profile_fingerprint="b" * 64,
            notional_usd=750.0,
        )


def _book(
    timestamp_ms: int,
    mid_price: float,
    *,
    run_id: str = "live-a",
    symbol: str = "BTC",
    fingerprint: str = "a" * 64,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "profile_id": f"profile-{symbol.lower()}",
        "profile_fingerprint": fingerprint,
        "event_type": "book_observation",
        "payload": {
            "recv_ts_ms": timestamp_ms,
            "mid_px": mid_price,
            "bids": [{"price": 99.9, "size": 100.0}],
            "asks": [{"price": 100.1, "size": 100.0}],
        },
    }


def _identity(symbol: str, profile_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "run_id": "live-a",
        "profile_id": profile_id,
        "profile_fingerprint": fingerprint,
        "event_type": "configuration_identity",
        "payload": {"symbol": symbol},
    }
