"""Point-in-time duration checkpoints for the pending V58 ETH lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.research.v58_eth_duration_checkpoint import (
    build_v58_eth_duration_checkpoint_report,
    load_v58_eth_duration_checkpoint_report,
)

_RUN = "bidirectional-observe-v58"
_PROFILE = "v58-profile-fingerprint"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"
_DECISION_MS = 1_800_000_000_000
_ENTRY_MS = _DECISION_MS + 10_000
_FOUR_HOURS_MS = 240 * 60_000
_EIGHT_HOURS_MS = 480 * 60_000


def test_reconciles_same_entry_at_four_and_eight_hour_boundaries() -> None:
    """Both checkpoints reuse the frozen entry and exact first later book."""
    report = build_v58_eth_duration_checkpoint_report(_status(), _records())

    four = report["duration_checkpoints"]["fixed_240m"]
    eight = report["duration_checkpoints"]["fixed_480m"]
    assert four["entry_time_ms"] == eight["entry_time_ms"] == _ENTRY_MS
    assert four["exit_time_ms"] == _ENTRY_MS + _FOUR_HOURS_MS + 500
    assert eight["exit_time_ms"] == _ENTRY_MS + _EIGHT_HOURS_MS + 500
    assert four["exit_reason"] == eight["exit_reason"] == "maximum_hold"
    assert four["net_return_scope"] == "exact_depth_fee_and_funding"
    assert eight["net_return_bps"] > four["net_return_bps"] > 0.0
    assert report["retained_control"]["maximum_hold_minutes"] == 720
    assert report["retained_control"]["state"] == "awaiting_resolution"
    assert report["execution_authority"] == "none"
    assert report["strategy_change_supported"] is False


def test_freezes_retained_control_snapshot_at_publication() -> None:
    """The mutable source status is preserved as contemporaneous control evidence."""
    report = build_v58_eth_duration_checkpoint_report(_status(), _records())

    snapshot = report["retained_control_snapshot"]
    assert snapshot == {
        "status": "exit_pending",
        "snapshot_time_ms": _ENTRY_MS + _EIGHT_HOURS_MS + 10_000,
        "current_exit_price": 102.2,
        "current_gross_return_bps": 220.0,
        "current_fee_bps": 9.0,
        "current_funding_bps": 1.0,
        "current_net_return_bps": 210.0,
        "current_simulated_net_pnl_usd": 15.75,
        "net_return_scope": "exact_depth_fee_and_funding",
        "same_timestamp_as_fixed_480m": False,
        "actual_exit_fill_claim": False,
    }


def test_rejects_incomplete_retained_control_funding() -> None:
    """A control mark without exact funding cannot become durable evidence."""
    status = _status()
    status["latest_attempts"][0]["net_return_scope"] = "fees_only"

    with pytest.raises(ValueError, match="retained control funding"):
        build_v58_eth_duration_checkpoint_report(status, _records())


def test_uses_earlier_protective_exit_instead_of_timer() -> None:
    """The diagnostic preserves stop-before-timer ordering."""
    records = _records()
    records.insert(
        3,
        _row(
            "market_books",
            _books(99.3, 99.4, _ENTRY_MS + 60_000),
            _ENTRY_MS + 60_000,
        ),
    )

    report = build_v58_eth_duration_checkpoint_report(_status(), records)

    for checkpoint in report["duration_checkpoints"].values():
        assert checkpoint["exit_reason"] == "protective_stop"
        assert checkpoint["exit_time_ms"] == _ENTRY_MS + 60_000


def test_ignores_prior_technical_incomplete_attempt() -> None:
    """A prior censored attempt cannot block the unique pending lifecycle."""
    status = _status()
    prior = dict(
        status["latest_attempts"][0],
        status="active_book_path_gap",
        decision_time_ms=_DECISION_MS - 60_000,
        entry_time_ms=_ENTRY_MS - 60_000,
        deadline_time_ms=_ENTRY_MS - 60_000 + 720 * 60_000,
    )
    status["latest_attempts"].insert(0, prior)

    report = build_v58_eth_duration_checkpoint_report(status, _records())

    assert report["source_lifecycle"]["decision_time_ms"] == _DECISION_MS


def test_rejects_ambiguous_pending_attempts() -> None:
    """Two pending lifecycles must fail rather than select by recency."""
    status = _status()
    status["latest_attempts"].append(dict(status["latest_attempts"][0]))

    with pytest.raises(ValueError, match="one pending lifecycle"):
        build_v58_eth_duration_checkpoint_report(status, _records())


def test_rejects_drifted_source_contract() -> None:
    """A non-720-minute source cannot alias the frozen lifecycle."""
    status = _status()
    status["contract"]["maximum_hold_minutes"] = 480

    with pytest.raises(ValueError, match="source contract"):
        build_v58_eth_duration_checkpoint_report(status, _records())


def test_loader_binds_exact_status_and_ledger_prefix(tmp_path: Path) -> None:
    """The durable report identifies the exact status and ledger bytes used."""
    ledger = tmp_path / "decisions.jsonl"
    ledger_raw = b"".join(
        json.dumps(row, sort_keys=True).encode() + b"\n" for row in _records()
    )
    ledger.write_bytes(ledger_raw)
    status = _status()
    status["source_evidence"]["ledger"] = {
        "path": str(ledger),
        "stable_bytes": len(ledger_raw),
        "sha256": hashlib.sha256(ledger_raw).hexdigest(),
    }
    status_path = tmp_path / "status.json"
    status_raw = json.dumps(status, sort_keys=True).encode()
    status_path.write_bytes(status_raw)

    report = load_v58_eth_duration_checkpoint_report(status_path)

    assert (
        report["source_evidence"]["status"]["sha256"]
        == hashlib.sha256(status_raw).hexdigest()
    )
    assert (
        report["source_evidence"]["observer_ledger"]["sha256"]
        == hashlib.sha256(ledger_raw).hexdigest()
    )
    generator = report["source_evidence"]["checkpoint_generator"]
    generator_path = Path(generator["path"])
    assert generator_path.name == "v58_eth_duration_checkpoint.py"
    assert (
        generator["sha256"] == hashlib.sha256(generator_path.read_bytes()).hexdigest()
    )
    assert report["generated_at_utc"].endswith("+00:00")


def _status() -> dict[str, object]:
    current_ms = _ENTRY_MS + _EIGHT_HOURS_MS + 10_000
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "awaiting_resolution",
        "contract": _status_contract(),
        "latest_attempts": [
            {
                "source_run_id": _RUN,
                "strategy_id": _STRATEGY,
                "candidate_strategy_id": _CANDIDATE,
                "symbol": "ETH",
                "side": "long",
                "decision_time_ms": _DECISION_MS,
                "available_time_ms": _DECISION_MS,
                "entry_time_ms": _ENTRY_MS,
                "deadline_time_ms": _ENTRY_MS + 720 * 60_000,
                "current_exit_time_ms": current_ms,
                "current_exit_price": 102.2,
                "current_gross_return_bps": 220.0,
                "current_fee_bps": 9.0,
                "current_funding_bps": 1.0,
                "current_net_return_bps": 210.0,
                "current_simulated_net_pnl_usd": 15.75,
                "net_return_scope": "exact_depth_fee_and_funding",
                "status": "exit_pending",
            }
        ],
        "latest_executions": [],
        "source_evidence": {
            "funding": {
                "status": "covered",
                "source": "hl_funding_history",
                "symbol": "ETH",
                "requested_start_ms": _ENTRY_MS,
                "requested_end_ms": current_ms,
                "events": [
                    {
                        "timestamp_ms": _ENTRY_MS + 60 * 60_000,
                        "funding_rate": -0.00001,
                    }
                ],
            }
        },
    }


def _status_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": "ETH",
        "source_run_id": _RUN,
        "profile_fingerprint": _PROFILE,
        "compatible_run_ids": [_RUN],
        "stop_bps": 60.0,
        "notional_usd": 750.0,
        "maximum_hold_minutes": 720,
        "close_on_eligible_opposite_signal": True,
        "same_cycle_reversal": False,
        "taker_fee_rate": 0.00045,
    }


def _records() -> list[dict[str, object]]:
    return [
        _row("configuration_identity", _identity(), _DECISION_MS - 1_000),
        _row("intent_routing", _routing(), _DECISION_MS),
        _row("market_books", _books(99.9, 100.0, _ENTRY_MS), _ENTRY_MS),
        *_continuous_path_books(),
        _row(
            "market_books",
            _books(101.0, 101.1, _ENTRY_MS + _FOUR_HOURS_MS + 500),
            _ENTRY_MS + _FOUR_HOURS_MS + 500,
        ),
        _row(
            "market_books",
            _books(102.0, 102.1, _ENTRY_MS + _EIGHT_HOURS_MS + 500),
            _ENTRY_MS + _EIGHT_HOURS_MS + 500,
        ),
        _row(
            "market_books",
            _books(102.2, 102.3, _ENTRY_MS + _EIGHT_HOURS_MS + 10_000),
            _ENTRY_MS + _EIGHT_HOURS_MS + 10_000,
        ),
    ]


def _continuous_path_books() -> list[dict[str, object]]:
    """Return sub-minute books without occupying either duration boundary."""
    rows = []
    for offset in range(59_500, _EIGHT_HOURS_MS, 60_000):
        observed_ms = _ENTRY_MS + offset
        rows.append(
            _row("market_books", _books(100.4, 100.5, observed_ms), observed_ms)
        )
    return rows


def _identity() -> dict[str, object]:
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "profile_fingerprint": _PROFILE,
        "enabled_symbols": ["ETH"],
    }


def _routing() -> dict[str, object]:
    return {
        "evaluations": [
            {
                "strategy_id": _STRATEGY,
                "symbol": "ETH",
                "decision_time_ms": _DECISION_MS,
                "reference_price": 100.0,
                "decision_action": "enter_long",
                "eligible": True,
                "reason": "eth_breakout_transfer_ready",
                "side": "long",
                "readiness": {"side": "long", "blockers": [], "metrics": {}},
            }
        ],
        "actions": [],
        "withheld": [],
    }


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
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_fingerprint": "observer-run-fingerprint",
        "run_id": _RUN,
        "payload": payload,
    }
