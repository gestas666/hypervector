"""Exact sampled excursion context for the open V58 ETH lifecycle."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.v58_eth_open_path_context import (
    eth_open_path_context_payload,
    load_v58_eth_open_path_context,
)
from v58_eth_open_path_censored_fixture import (
    write_censored_status,
    write_censored_then_pending_status,
)
from v58_eth_open_path_history_fixture import (
    sha256_file as _sha256_file,
    source_history as _source_history,
)

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE = "profile"
_RUN = "bidirectional-observe-1787127644202"


def test_zero_lifecycle_reports_awaiting_without_sampled_claims(
    tmp_path: Path,
) -> None:
    """A quiet current run must not fabricate path or economic evidence."""
    status, _ = _pending_status(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["summary"].update(
        {"pending": 0, "resolved": 0, "selected_non_overlapping": 0}
    )
    payload["latest_attempts"] = []
    payload["latest_executions"] = []
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    journal = _source_history(tmp_path)

    context = load_v58_eth_open_path_context(
        status,
        source_history_journal=journal,
        expected_history_journal_sha256=_sha256_file(journal),
    )
    result = eth_open_path_context_payload(context)

    assert result["state"] == "awaiting_first_lifecycle"
    assert result["sampled_exit_vwap_claim"] is False
    assert result["excursion_metrics_are_gross_before_costs"] is False
    assert "current_net_return_bps" not in result
    assert result["source_compatible_lifecycle_summary"]["observed_lifecycles"] == 1


def test_pending_path_reports_sampled_excursion_and_ignores_future_append(
    tmp_path: Path,
) -> None:
    """MFE, MAE, giveback, and gaps must use the watcher's frozen prefix."""
    status, ledger = _pending_status(tmp_path)

    before = eth_open_path_context_payload(load_v58_eth_open_path_context(status))
    ledger.write_bytes(ledger.read_bytes() + _line(_book_row(5_000, 102.0)))
    after = eth_open_path_context_payload(load_v58_eth_open_path_context(status))

    assert after == before
    assert before["state"] == "open"
    assert before["sampled_exit_observations"] == 3
    assert before["maximum_favorable_excursion_bps"] == pytest.approx(100.0)
    assert before["maximum_adverse_excursion_bps"] == pytest.approx(50.0)
    assert before["current_gross_return_bps"] == pytest.approx(-30.0)
    assert before["current_fee_bps"] == pytest.approx(8.9865)
    assert before["current_funding_bps"] == pytest.approx(0.1)
    assert before["net_return_scope"] == "exact_depth_fee_and_funding"
    assert before["current_net_break_even_gross_bps"] == pytest.approx(8.8865)
    assert before["current_net_profit_observed"] is False
    assert before["maximum_sampled_net_return_bps"] == pytest.approx(90.955)
    assert before["maximum_sampled_net_return_time_ms"] == 2_000
    assert before["seconds_to_maximum_sampled_net_return"] == pytest.approx(1.0)
    assert before["maximum_sampled_net_pnl_usd"] == pytest.approx(6.821625)
    assert before["minimum_sampled_net_return_time_ms"] == 3_000
    assert before["first_sampled_net_profit_time_ms"] == 2_000
    assert before["seconds_to_first_sampled_net_profit"] == pytest.approx(1.0)
    assert before["sampled_net_return_giveback_bps"] == pytest.approx(129.8415)
    assert before["sampled_net_profit_observed"] is True
    assert before["peak_giveback_bps"] == pytest.approx(130.0)
    assert before["stop_headroom_bps"] == pytest.approx(10.0)
    assert before["maximum_observation_gap_ms"] == 1_000
    assert before["continuous_path_claim"] is False
    assert before["excursion_metrics_are_gross_before_costs"] is True
    assert before["execution_authority"] == "none"


def test_resolved_path_preserves_exit_reason_and_excursion(tmp_path: Path) -> None:
    """Resolution must retain the same path metrics through the frozen exit."""
    status, _ = _resolved_status(tmp_path)

    payload = eth_open_path_context_payload(load_v58_eth_open_path_context(status))

    assert payload["state"] == "resolved"
    assert payload["exit_reason"] == "maximum_hold"
    assert payload["maximum_favorable_excursion_bps"] == pytest.approx(100.0)
    assert payload["maximum_adverse_excursion_bps"] == pytest.approx(50.0)
    assert payload["current_gross_return_bps"] == pytest.approx(-30.0)
    assert payload["current_fee_bps"] == pytest.approx(8.9865)
    assert payload["current_funding_bps"] == pytest.approx(0.1)
    assert payload["net_return_scope"] == "exact_depth_fee_and_funding"
    assert payload["current_net_profit_observed"] is False
    assert payload["strategy_change_supported"] is False


def test_resolved_protective_stop_accepts_crossing_path(tmp_path: Path) -> None:
    """A sampled stop crossing is required evidence for a protective-stop exit."""
    status = _resolved_stop_status(tmp_path)

    payload = eth_open_path_context_payload(load_v58_eth_open_path_context(status))

    assert payload["state"] == "resolved"
    assert payload["exit_reason"] == "protective_stop"
    assert payload["maximum_adverse_excursion_bps"] == pytest.approx(70.0)
    assert payload["stop_headroom_bps"] == pytest.approx(-10.0)


def test_active_book_gap_is_censored_without_sampled_pnl_claim(tmp_path: Path) -> None:
    """A missing active path must remain technical evidence, not an outcome."""
    status, _ = _pending_status(tmp_path)
    write_censored_status(status)
    journal = _source_history(tmp_path)

    context = load_v58_eth_open_path_context(
        status,
        source_history_journal=journal,
        expected_history_journal_sha256=_sha256_file(journal),
    )
    payload = eth_open_path_context_payload(context)
    summary = payload["source_compatible_lifecycle_summary"]

    assert payload["state"] == "technically_censored"
    assert payload["technical_incomplete_reason"] == "active_book_path_gap"
    assert payload["maximum_active_book_gap_ms"] == 2_000
    assert payload["sampled_exit_vwap_claim"] is False
    assert payload["continuous_path_claim"] is False
    assert summary["resolved_lifecycles"] == 1
    assert summary["pending_lifecycles"] == 0
    assert summary["technical_incomplete"] == 1
    assert summary["realized_net_return_bps"] == pytest.approx(-69.13281563982316)


def test_new_pending_lifecycle_preserves_prior_censored_attempt(tmp_path: Path) -> None:
    """A later entry must become current without erasing prior technical evidence."""
    status, _ = _pending_status(tmp_path)
    write_censored_then_pending_status(status)
    journal = _source_history(tmp_path)

    context = load_v58_eth_open_path_context(
        status,
        source_history_journal=journal,
        expected_history_journal_sha256=_sha256_file(journal),
    )
    payload = eth_open_path_context_payload(context)
    summary = payload["source_compatible_lifecycle_summary"]

    assert payload["state"] == "open"
    assert payload["entry_time_ms"] == 1_000
    assert summary["observed_lifecycles"] == 3
    assert summary["resolved_lifecycles"] == 1
    assert summary["pending_lifecycles"] == 1
    assert summary["technical_incomplete"] == 1
    assert summary["censored_excluded_from_realized_totals"] is True


def test_path_rejects_unreconciled_fee_funding_net(tmp_path: Path) -> None:
    """Success-shaped economics must not enter the consolidated report."""
    status, _ = _pending_status(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["latest_attempts"][0]["current_funding_bps"] = 5.0
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="net return components do not reconcile"):
        load_v58_eth_open_path_context(status)


def test_path_rejects_taker_fee_contract_drift(tmp_path: Path) -> None:
    """The exact forward fee contract cannot silently change between cycles."""
    status, _ = _pending_status(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["contract"]["taker_fee_rate"] = 0.0002
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="path contract is invalid"):
        load_v58_eth_open_path_context(status)


def test_path_adds_distinct_prior_source_compatible_resolution(
    tmp_path: Path,
) -> None:
    """Cumulative evidence must retain prior loss and current pending state."""
    status, _ = _pending_status(tmp_path)
    journal = _source_history(tmp_path)

    context = load_v58_eth_open_path_context(
        status,
        source_history_journal=journal,
        expected_history_journal_sha256=_sha256_file(journal),
    )
    payload = eth_open_path_context_payload(context)
    summary = payload["source_compatible_lifecycle_summary"]

    assert summary["observed_lifecycles"] == 2
    assert summary["resolved_lifecycles"] == 1
    assert summary["pending_lifecycles"] == 1
    assert summary["long_lifecycles"] == 2
    assert summary["short_lifecycles"] == 0
    assert summary["both_sides_observed"] is False
    assert summary["realized_net_return_bps"] == pytest.approx(-69.13281563982316)
    assert summary["realized_net_pnl_usd"] == pytest.approx(-5.184961172986737)
    assert summary["pending_excluded_from_realized_totals"] is True
    assert summary["strategy_change_supported"] is False
    assert context.evidence["source_compatible_history"]["artifact"]["sha256"]


def test_path_rejects_changed_prior_source_artifact(tmp_path: Path) -> None:
    """A journal cannot authorize changed historical lifecycle bytes."""
    status, _ = _pending_status(tmp_path)
    journal = _source_history(tmp_path)
    payload = json.loads(journal.read_text(encoding="utf-8"))
    artifact = Path(payload["source_evidence"][0]["path"])
    artifact.write_bytes(artifact.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source artifact identity"):
        load_v58_eth_open_path_context(
            status,
            source_history_journal=journal,
            expected_history_journal_sha256=_sha256_file(journal),
        )


def test_path_rejects_duplicate_prior_and_current_run(tmp_path: Path) -> None:
    """One observer run must not be counted as two compatible lifecycles."""
    status, _ = _pending_status(tmp_path)
    journal = _source_history(tmp_path, prior_run=_RUN)

    with pytest.raises(ValueError, match="distinct observer runs"):
        load_v58_eth_open_path_context(
            status,
            source_history_journal=journal,
            expected_history_journal_sha256=_sha256_file(journal),
        )


def _pending_status(tmp_path: Path) -> tuple[Path, Path]:
    ledger = tmp_path / "decisions.jsonl"
    rows = [_book_row(500, 50.0, run_id="prior-observer-run")]
    rows.extend(
        _book_row(timestamp, price)
        for timestamp, price in (
            (1_000, 99.99),
            (2_000, 101.0),
            (3_000, 99.5),
            (4_000, 99.7),
        )
    )
    prefix = b"".join(_line(row) for row in rows)
    ledger.write_bytes(prefix)
    status = tmp_path / "eth.json"
    status.write_text(
        json.dumps(_status_payload(ledger, prefix), sort_keys=True), encoding="utf-8"
    )
    return status, ledger


def _resolved_status(tmp_path: Path) -> tuple[Path, Path]:
    status, ledger = _pending_status(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    pending = payload["latest_attempts"][0]
    execution = {
        **pending,
        "status": "resolved",
        "exit_reason": "maximum_hold",
        "exit_time_ms": pending.pop("current_exit_time_ms"),
        "exit_price": pending.pop("current_exit_price"),
        "gross_return_bps": pending.pop("current_gross_return_bps"),
        "fee_bps": pending.pop("current_fee_bps"),
        "funding_bps": pending.pop("current_funding_bps"),
        "net_return_bps": pending.pop("current_net_return_bps"),
        "simulated_net_pnl_usd": pending.pop("current_simulated_net_pnl_usd"),
    }
    payload["state"] = "descriptive_exact_depth_evidence"
    payload["summary"].update({"pending": 0, "resolved": 1})
    payload["latest_attempts"] = [
        {"status": "resolved", "decision_time_ms": execution["decision_time_ms"]}
    ]
    payload["latest_executions"] = [execution]
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return status, ledger


def _resolved_stop_status(tmp_path: Path) -> Path:
    status, ledger = _resolved_status(tmp_path)
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[-1] = _book_row(4_000, 99.3)
    prefix = b"".join(_line(row) for row in rows)
    ledger.write_bytes(prefix)
    payload = json.loads(status.read_text(encoding="utf-8"))
    execution = payload["latest_executions"][0]
    execution.update(
        {
            "exit_reason": "protective_stop",
            "exit_price": 99.3,
            "gross_return_bps": -70.0,
            "fee_bps": 8.9685,
            "net_return_bps": -78.8685,
            "simulated_net_pnl_usd": -5.9151375,
        }
    )
    payload["source_evidence"]["ledger"].update(
        {"stable_bytes": len(prefix), "sha256": sha256(prefix).hexdigest()}
    )
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return status


def _status_payload(ledger: Path, prefix: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "awaiting_resolution",
        "contract": _contract(),
        "identity": {
            "profile_id": _PROFILE_ID,
            "profile_fingerprint": _PROFILE,
            "source_run_id": _RUN,
            "compatible_run_ids": [_RUN],
        },
        "summary": {
            "pending": 1,
            "resolved": 0,
            "technical_incomplete": 0,
            "selected_non_overlapping": 1,
            "overlapping_excluded": 0,
        },
        "latest_attempts": [_pending_attempt()],
        "latest_executions": [],
        "source_evidence": {
            "ledger": {
                "path": str(ledger),
                "stable_bytes": len(prefix),
                "sha256": sha256(prefix).hexdigest(),
            },
            "funding": {
                "source": "hl_funding_history",
                "status": "covered",
                "symbol": "ETH",
                "requested_start_ms": 1_000,
                "requested_end_ms": 4_000,
                "events": [{"timestamp_ms": 2_500, "funding_rate": -0.00001}],
            },
        },
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward",
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


def _pending_attempt() -> dict[str, object]:
    return {
        "status": "exit_pending",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward",
        "symbol": "ETH",
        "source_run_id": _RUN,
        "side": "long",
        "decision_time_ms": 500,
        "available_time_ms": 900,
        "entry_time_ms": 1_000,
        "entry_price": 100.0,
        "position_quantity": 7.5,
        "entry_notional_usd": 750.0,
        "deadline_time_ms": 43_201_000,
        "current_exit_time_ms": 4_000,
        "current_exit_price": 99.7,
        "current_gross_return_bps": -30.0,
        "current_fee_bps": 8.9865,
        "current_funding_bps": 0.1,
        "net_return_scope": "exact_depth_fee_and_funding",
        "current_net_return_bps": -38.8865,
        "current_simulated_net_pnl_usd": -2.9164875,
    }


def _book_row(
    timestamp: int, exit_bid: float, *, run_id: str = _RUN
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": timestamp,
        "event_type": "market_books",
        "observed_at_utc": "2026-08-19T12:00:00+00:00",
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": _PROFILE,
        "run_fingerprint": "run-profile",
        "run_id": run_id,
        "payload": {
            "books": {
                "ETH": {
                    "symbol": "ETH",
                    "source": "hyperliquid_mainnet_l2_rest",
                    "exchange_ts_ms": timestamp - 1,
                    "recv_ts_ms": timestamp,
                    "mid_px": exit_bid + 0.005,
                    "spread_bps": 1.0,
                    "bid_depth_ratio": 0.5,
                    "opi": 0.0,
                    "bids": [{"price": exit_bid, "size": 100.0, "orders": 1}],
                    "asks": [{"price": exit_bid + 0.01, "size": 100.0, "orders": 1}],
                }
            }
        },
    }


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
