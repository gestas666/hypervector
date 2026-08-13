"""Visible-depth execution policy for one-blocker replay."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    build_one_blocker_execution_feasibility,
)

_DECISION_MS = 1_800_000_000_000


def test_visible_depth_resolves_when_top_level_is_thin() -> None:
    """Explicit depth mode prices entry and exit VWAP across visible levels."""
    report = build_one_blocker_execution_feasibility(
        _cohort(),
        {"HYPE": _books()},
        (),
        contract=_contract("visible_depth"),
    )

    trade = report["executions"][0]
    assert report["coverage"]["resolved_executions"] == 1
    assert trade["entry_price"] == pytest.approx(100.18998100189982)
    assert trade["exit_price"] < 100.0
    assert report["contract"]["liquidity_rule"] == (
        "entire_notional_visible_within_recorded_depth"
    )


def test_default_top_level_policy_preserves_strict_failure() -> None:
    """Existing evidence retains its original strict BBO capacity contract."""
    report = build_one_blocker_execution_feasibility(
        _cohort(),
        {"HYPE": _books()},
        (),
        contract=_contract("top_level"),
    )

    assert report["coverage"]["entry_capacity_failures"] == 1
    assert report["executions"] == []


def _contract(policy: str) -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id="hype_breakout_compression_pullback_bidirectional_v1",
        symbol="HYPE",
        blocker="canonical_breakout_onset_absent",
        horizon_minutes=1,
        maximum_context_age_ms=30_000,
        maximum_entry_delay_ms=30_000,
        maximum_exit_delay_ms=30_000,
        notional_usd=100.0,
        taker_fee_rate=0.000432,
        stop_proxy_bps=80.0,
        opi_cohort="all",
        liquidity_policy=policy,
    )


def _cohort() -> tuple[dict[str, object], ...]:
    evaluation = {
        "strategy_id": "hype_breakout_compression_pullback_bidirectional_v1",
        "symbol": "HYPE",
        "decision_time_ms": _DECISION_MS,
        "reference_price": 100.0,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": ["canonical_breakout_onset_absent"],
            "metrics": {},
        },
    }
    return (
        _row("configuration_identity", {}, _DECISION_MS - 60_000),
        _row("intent_routing", {"evaluations": [evaluation]}, _DECISION_MS + 1_000),
    )


def _books() -> tuple[dict[str, object], ...]:
    return (
        _book(_DECISION_MS, 99.9, 100.0),
        _book(_DECISION_MS + 2_000, 100.0, 100.1),
        _book(_DECISION_MS + 62_000, 100.0, 100.1),
    )


def _book(observed_ms: int, bid: float, ask: float) -> dict[str, object]:
    return _row(
        "book_observation",
        {
            "recv_ts_ms": observed_ms,
            "exchange_ts_ms": observed_ms - 10,
            "opi": 0.4,
            "mid_px": (bid + ask) / 2.0,
            "bids": [
                {"price": bid, "size": 0.1},
                {"price": bid - 0.1, "size": 2.0},
            ],
            "asks": [
                {"price": ask, "size": 0.1},
                {"price": ask + 0.1, "size": 2.0},
            ],
        },
        observed_ms,
    )


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "payload": payload,
    }
