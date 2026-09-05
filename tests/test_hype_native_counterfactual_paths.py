"""Exact-depth tests for HYPE-native counterfactual paths."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from hypervector.research.hype_native_counterfactual_paths import (
    HypeNativePathSpec,
    build_hype_native_counterfactual_path,
)


def test_path_anchors_entry_after_publication_and_resolves_bbo_stop() -> None:
    """A native onset must use the first causal executable depth after publication."""
    report = build_hype_native_counterfactual_path(
        _cohort_rows(),
        _asset_rows(stop=True),
        _spec(),
    )

    source = report["source_signal"]
    execution = report["execution_path"]
    assert source["available_time_ms"] == 67_000
    assert source["source_eligible"] is False
    assert execution["entry_book_time_ms"] == 70_000
    assert execution["entry_price"] == pytest.approx(100.01)
    assert execution["stop_price"] == pytest.approx(99.20992)
    assert execution["exit_reason"] == "protective_stop_bbo_proxy"
    assert execution["exit_book_time_ms"] == 130_000
    assert execution["net_pnl_usd_before_funding"] < -10.0
    assert report["status"] == "resolved_bbo_stop_proxy_mark_trigger_unverified"


def test_open_path_reports_exact_horizons_without_claiming_realized_profit() -> None:
    """A favorable unfinished path remains pending and explicitly counterfactual."""
    report = build_hype_native_counterfactual_path(
        _cohort_rows(),
        _asset_rows(stop=False),
        _spec(),
    )

    path = report["execution_path"]
    assert path["exit_reason"] is None
    assert path["current_net_pnl_usd_before_funding"] > 0.0
    resolved = path["horizons"]["1"]
    assert resolved["status"] == "resolved_bbo_proxy"
    assert resolved["target_time_ms"] == 130_000
    assert resolved["book_time_ms"] == 130_000
    assert resolved["book_delay_ms"] == 0
    assert path["horizons"]["5"]["status"] == "censored"
    assert report["status"] == "open_counterfactual_path"
    assert report["contract"]["realized_pnl_claimed"] is False
    assert (
        report["limitations"][0]
        == "recorded BBO does not prove a venue mark-price stop trigger"
    )


def test_noncanonical_source_onset_fails_closed() -> None:
    """An ordinary compression evaluation cannot be relabeled as native onset."""
    rows = _cohort_rows()
    evaluation = rows[1]["payload"]["evaluations"][0]
    evaluation["readiness"]["metrics"]["canonical_breakout_onset_fresh"] = False

    with pytest.raises(ValueError, match="canonical breakout onset"):
        build_hype_native_counterfactual_path(rows, _asset_rows(stop=False), _spec())


def test_bounded_cross_clock_skew_is_disclosed_and_larger_skew_aborts() -> None:
    """Exchange/local clock skew may be bounded, but it cannot be hidden."""
    rows = _asset_rows(stop=False)
    book = rows[-1]["payload"]
    book["exchange_ts_ms"] = book["recv_ts_ms"] + 1_750
    spec = replace(_spec(), maximum_clock_skew_ms=2_000)

    report = build_hype_native_counterfactual_path(_cohort_rows(), rows, spec)

    assert report["market_clock_evidence"] == {
        "maximum_allowed_exchange_ahead_ms": 2_000,
        "exchange_ahead_row_count": 1,
        "maximum_exchange_ahead_ms": 1_750,
    }
    book["exchange_ts_ms"] = book["recv_ts_ms"] + 2_001
    with pytest.raises(ValueError, match="maximum allowed clock skew"):
        build_hype_native_counterfactual_path(_cohort_rows(), rows, spec)


def _spec() -> HypeNativePathSpec:
    return HypeNativePathSpec(
        run_id="run-v53",
        profile_id="profile-v53",
        profile_fingerprint="c" * 64,
        source_strategy_id="hype_breakout_compression_alignment_bidirectional_v2",
        candidate_strategy_id="hype_native_breakout_onset_bidirectional_v2",
        symbol="HYPE",
        side="long",
        decision_time_ms=60_000,
        notional_usd=1_250.0,
        stop_bps=80.0,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
        soft_hold_seconds=28_800,
        hard_hold_seconds=86_400,
        fee_bps_per_side=4.32,
        residual_slippage_bps_per_side=2.0,
        maximum_clock_skew_ms=0,
        horizons_minutes=(1, 5),
    )


def _cohort_rows() -> list[dict[str, object]]:
    return [
        {
            "event_type": "configuration_identity",
            "observed_at_utc": _utc(0),
            "run_id": "run-v53",
            "profile_id": "profile-v53",
            "profile_fingerprint": "c" * 64,
            "payload": {
                "providers": [
                    {
                        "strategy_id": "hype_breakout_compression_alignment_bidirectional_v2",
                        "symbols": ["HYPE"],
                        "sides": ["long", "short"],
                    }
                ]
            },
        },
        _routing(60_000, 67_000, "long", True),
        _routing(180_000, 187_000, "long", False),
    ]


def _routing(
    decision_ms: int, observed_ms: int, side: str, onset: bool
) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "observed_at_utc": _utc(observed_ms),
        "run_id": "run-v53",
        "profile_id": "profile-v53",
        "profile_fingerprint": "c" * 64,
        "payload": {
            "evaluations": [
                {
                    "strategy_id": "hype_breakout_compression_alignment_bidirectional_v2",
                    "symbol": "HYPE",
                    "decision_time_ms": decision_ms,
                    "reference_price": 100.0,
                    "decision_action": "hold",
                    "eligible": False,
                    "reason": "authoritative_5m_compression_absent",
                    "side": side,
                    "primary_regime": "BREAKOUT",
                    "state_1m": "TREND_UP",
                    "state_5m": "BREAKOUT",
                    "context_15m": "TREND_UP",
                    "readiness": {
                        "side": side,
                        "blockers": ["authoritative_5m_compression_absent"],
                        "metrics": {
                            "canonical_breakout_onset_fresh": onset,
                            "structural_direction": side,
                        },
                    },
                }
            ]
        },
    }


def _asset_rows(*, stop: bool) -> list[dict[str, object]]:
    prices = [(65_000, 100.0, 100.01), (70_000, 100.0, 100.01)]
    prices.append((130_000, 99.1 if stop else 101.0, 99.11 if stop else 101.01))
    return [_asset_identity(), *[_book(*values) for values in prices]]


def _asset_identity() -> dict[str, object]:
    return {
        "event_type": "configuration_identity",
        "observed_at_utc": _utc(0),
        "run_id": "run-v53",
        "profile_id": "profile-v53-hype",
        "profile_fingerprint": "a" * 64,
        "payload": {"symbol": "HYPE"},
    }


def _book(timestamp_ms: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "observed_at_utc": _utc(timestamp_ms),
        "run_id": "run-v53",
        "profile_id": "profile-v53-hype",
        "profile_fingerprint": "a" * 64,
        "payload": {
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": timestamp_ms - 10,
            "recv_ts_ms": timestamp_ms,
            "bids": _levels(bid, -0.01),
            "asks": _levels(ask, 0.01),
        },
    }


def _levels(start: float, step: float) -> list[dict[str, float]]:
    return [{"price": start + step * index, "size": 1_000.0} for index in range(20)]


def _utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC).isoformat()
