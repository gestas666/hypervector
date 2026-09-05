"""Exact-depth forward resolution for the isolated ETH pullback observer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    EligiblePolicyFundingEvent,
)
from hypervector.research.eth_pullback_forward_resolution import (
    build_eth_pullback_forward_resolution,
    eth_pullback_funding_bounds,
)

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / "configs/research/multi_asset_eth_pullback_forward_observer_v1.toml"
_JOURNAL = _ROOT / "docs/research-journal/eth-breakout-precompression-pullback-v14.json"
_RUN = "bidirectional-observe-eth"
_DECISION = 1_800_000_000_000


def test_resolves_eligible_long_through_exact_depth_stop_and_funding() -> None:
    """The frozen route uses visible depth, its stop, fees, and funding."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    funding = EligiblePolicyFundingEvidence(
        symbol="ETH",
        requested_start_ms=_DECISION,
        requested_end_ms=_DECISION + 30_000,
        events=(
            EligiblePolicyFundingEvent(
                timestamp_ms=_DECISION + 15_000,
                funding_rate=0.00001,
            ),
        ),
    )

    report = build_eth_pullback_forward_resolution(
        _records(config.profile_fingerprint),
        config=config,
        run_id=_RUN,
        funding_evidence=funding,
        taker_fee_rate=0.00045,
    )

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "protective_stop"
    assert execution["funding_bps"] == pytest.approx(-0.1)
    assert execution["net_return_bps"] < -69.0
    assert report["contract"]["notional_usd"] == 750.0
    assert report["contract"]["close_on_eligible_opposite_signal"] is True
    assert report["contract"]["protective_stop_trigger_evidence"] == (
        "adverse_recorded_bbo_proxy"
    )
    assert eth_pullback_funding_bounds(report) == (
        _DECISION + 10_000,
        _DECISION + 20_000,
    )


def test_rejects_wrong_profile_identity() -> None:
    """A different observer profile cannot alias the frozen ETH route."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    with pytest.raises(ValueError, match="profile fingerprint"):
        build_eth_pullback_forward_resolution(
            _records("wrong-profile"),
            config=config,
            run_id=_RUN,
            funding_evidence=None,
            taker_fee_rate=0.00045,
        )


def test_excludes_eligible_signal_before_prospective_start() -> None:
    """A preregistered window cannot consume an earlier eligible signal."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    records = _records(config.profile_fingerprint)
    records.append(
        _row(
            "market_books",
            _books(100.0, 100.1, _DECISION + 70_000),
            _DECISION + 70_000,
        )
    )

    report = build_eth_pullback_forward_resolution(
        records,
        config=config,
        run_id=_RUN,
        prospective_start_ms=_DECISION + 60_000,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    assert report["summary"]["selected_non_overlapping"] == 0
    assert report["latest_attempts"] == []
    assert report["identity"]["prospective_start_ms"] == _DECISION + 60_000


def test_resolves_eligible_opposite_signal_without_reversal() -> None:
    """The ETH diagnostic must match the live enter-and-close exit contract."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    report = build_eth_pullback_forward_resolution(
        _opposite_records(config.profile_fingerprint),
        config=config,
        run_id=_RUN,
        funding_evidence=EligiblePolicyFundingEvidence(
            symbol="ETH",
            requested_start_ms=_DECISION,
            requested_end_ms=_DECISION + 70_000,
            events=(),
        ),
        taker_fee_rate=0.00045,
    )

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "opposite_strategy_intent"
    assert execution["exit_time_ms"] == _DECISION + 70_000
    assert report["summary"]["selected_non_overlapping"] == 1
    assert report["summary"]["overlapping_excluded"] == 1
    assert report["contract"]["same_cycle_reversal"] is False


def test_v14_journal_rejects_live_addition_and_reconciles_resolution() -> None:
    """The first exact forward loss must close the immediate ETH proposal."""
    payload = json.loads(_JOURNAL.read_text())
    evidence = payload["source_evidence"][0]
    source = _ROOT / evidence["path"]
    raw = source.read_bytes()

    assert payload["status"] == "first_exact_eligible_lifecycle_adverse"
    assert payload["recommendation"]["proposed_live_change"] == "none"
    assert payload["recommendation"]["explicit_approval_requested"] is False
    assert payload["exact_forward_lifecycle"]["net_return_bps"] < -69.0
    assert hashlib.sha256(raw).hexdigest() == evidence["sha256"]


def _records(fingerprint: str) -> list[dict[str, object]]:
    return [
        _row("configuration_identity", _identity(fingerprint), _DECISION - 1_000),
        _row("intent_routing", _routing(), _DECISION),
        _row(
            "market_books",
            _books(99.9, 100.0, _DECISION + 10_000),
            _DECISION + 10_000,
        ),
        _row(
            "market_books",
            _books(99.3, 99.4, _DECISION + 20_000),
            _DECISION + 20_000,
        ),
    ]


def _opposite_records(fingerprint: str) -> list[dict[str, object]]:
    opposite = _routing()["evaluations"][0]
    assert isinstance(opposite, dict)
    opposite = {
        **opposite,
        "decision_time_ms": _DECISION + 60_000,
        "reference_price": 100.4,
        "decision_action": "enter_short",
        "side": "short",
        "readiness": {"side": "short", "blockers": [], "metrics": {}},
    }
    return [
        _row("configuration_identity", _identity(fingerprint), _DECISION - 1_000),
        _row("intent_routing", _routing(), _DECISION),
        _row(
            "market_books",
            _books(99.9, 100.0, _DECISION + 10_000),
            _DECISION + 10_000,
        ),
        _row(
            "intent_routing",
            {"evaluations": [opposite], "actions": [], "withheld": []},
            _DECISION + 61_000,
        ),
        _row(
            "market_books",
            _books(100.3, 100.4, _DECISION + 70_000),
            _DECISION + 70_000,
        ),
    ]


def _identity(fingerprint: str) -> dict[str, object]:
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "profile_fingerprint": fingerprint,
        "enabled_symbols": ["ETH"],
    }


def _routing() -> dict[str, object]:
    evaluation = {
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "decision_time_ms": _DECISION,
        "reference_price": 100.0,
        "decision_action": "enter_long",
        "eligible": True,
        "reason": "eth_breakout_transfer_ready",
        "side": "long",
        "readiness": {"side": "long", "blockers": [], "metrics": {}},
    }
    return {"evaluations": [evaluation], "actions": [], "withheld": []}


def _books(bid: float, ask: float, recv_ms: int) -> dict[str, object]:
    return {
        "books": {
            "ETH": {
                "symbol": "ETH",
                "source": "hyperliquid_mainnet_l2_rest",
                "exchange_ts_ms": recv_ms - 50,
                "recv_ts_ms": recv_ms,
                "bids": [{"price": bid, "size": 20.0, "orders": 1}],
                "asks": [{"price": ask, "size": 20.0, "orders": 1}],
            }
        }
    }


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "run_fingerprint": "observer-run-fingerprint",
        "run_id": _RUN,
        "payload": payload,
    }
