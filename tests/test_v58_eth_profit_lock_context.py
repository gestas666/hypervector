"""Prospective ETH profit-lock context for the V58 research loop."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.v58_eth_exit_research_context import EthExitResearchContext
from hypervector.research.v58_eth_profit_lock_context import (
    eth_profit_lock_context_payload,
    load_v58_eth_profit_lock_context,
)

_RUN = "bidirectional-observe-1787127644202"
_PROFILE = "profile"


def test_context_withholds_policy_results_before_first_lifecycle(
    tmp_path: Path,
) -> None:
    """A quiet current run must remain unavailable instead of scoring locks."""
    status, _ = _sources(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["summary"].update(
        {"pending": 0, "resolved": 0, "selected_non_overlapping": 0}
    )
    payload["latest_attempts"] = []
    payload["latest_executions"] = []
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    context = eth_profit_lock_context_payload(
        load_v58_eth_profit_lock_context(status, _history())
    )

    assert context["lifecycle_state"] == "awaiting_first_lifecycle"
    assert context["evaluation_status"] == "unavailable_no_current_lifecycle"
    assert context["policies"] == {}
    assert "current_exact_net_excluding_funding_bps" not in context
    assert context["strategy_change_supported"] is False


def test_context_uses_frozen_prefix_and_preserves_historical_rejection(
    tmp_path: Path,
) -> None:
    """Future appends cannot alter a causal, authority-none lock snapshot."""
    status, ledger = _sources(tmp_path)
    history = _history()

    before = eth_profit_lock_context_payload(
        load_v58_eth_profit_lock_context(status, history)
    )
    ledger.write_bytes(ledger.read_bytes() + _line(_candle_row(180_000, 90.0)))
    after = eth_profit_lock_context_payload(
        load_v58_eth_profit_lock_context(status, history)
    )

    assert after == before
    assert before["lifecycle_state"] == "open"
    assert before["completed_bars_expected"] == 2
    assert before["completed_bars_observed"] == 2
    assert before["historical_disposition"] == "rejected_in_both_source_partitions"
    assert before["policies"]["a25_floor15_trail10"]["status"] == (
        "triggered_before_current_boundary"
    )
    assert before["strategy_change_supported"] is False
    assert before["execution_authority"] == "none"


def test_context_rejects_incomplete_historical_disposition(tmp_path: Path) -> None:
    """A current winner cannot silently erase a prior rejected-policy record."""
    status, _ = _sources(tmp_path)
    history = _history()
    history.payload["rejected_profit_locks"] = ["profit_a25_floor15_trail10"]

    with pytest.raises(ValueError, match="historical policy set"):
        load_v58_eth_profit_lock_context(status, history)


def test_context_withholds_counterfactual_for_censored_active_path(
    tmp_path: Path,
) -> None:
    """A source gap cannot become a success-shaped profit-lock comparison."""
    status, _ = _sources(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    attempt = payload["latest_attempts"][0]
    attempt["status"] = "active_book_path_gap"
    attempt.pop("current_exit_price")
    attempt.pop("current_gross_return_bps")
    attempt.pop("current_fee_bps")
    attempt.pop("current_funding_bps")
    attempt.pop("current_net_return_bps")
    attempt["maximum_active_book_gap_ms"] = 120_000
    attempt["maximum_allowed_active_book_gap_ms"] = 60_000
    attempt["active_book_gap_start_ms"] = 60_000
    attempt["active_book_gap_end_ms"] = 180_000
    attempt["deadline_time_ms"] = 300_000
    payload["summary"].update({"pending": 0, "technical_incomplete": 1})
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    context = eth_profit_lock_context_payload(
        load_v58_eth_profit_lock_context(status, _history())
    )

    assert context["lifecycle_state"] == "technically_censored"
    assert context["evaluation_status"] == "unavailable_active_book_path_gap"
    assert context["policies"] == {}
    assert context["strategy_change_supported"] is False


def test_context_uses_latest_pending_after_censored_attempt(tmp_path: Path) -> None:
    """Earlier technical evidence must not hide a newer active lifecycle."""
    status, _ = _sources(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    pending = payload["latest_attempts"][0]
    censored = {
        **pending,
        "status": "active_book_path_gap",
        "decision_time_ms": 50,
        "entry_time_ms": 5_000,
        "current_exit_time_ms": 9_000,
        "maximum_active_book_gap_ms": 2_000,
        "maximum_allowed_active_book_gap_ms": 1_000,
        "active_book_gap_start_ms": 6_000,
        "active_book_gap_end_ms": 8_000,
        "deadline_time_ms": 9_500,
    }
    payload["latest_attempts"] = [censored, pending]
    payload["summary"].update(
        {"pending": 1, "technical_incomplete": 1, "selected_non_overlapping": 2}
    )
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    context = eth_profit_lock_context_payload(
        load_v58_eth_profit_lock_context(status, _history())
    )

    assert context["lifecycle_state"] == "open"
    assert context["policies"]


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    ledger = tmp_path / "decisions.jsonl"
    prefix = b"".join(
        _line(row)
        for row in (
            _candle_row(60_000, 100.2, high=100.3, low=99.95),
            _candle_row(120_000, 100.2, high=100.25, low=100.18),
        )
    )
    ledger.write_bytes(prefix)
    status = tmp_path / "eth.json"
    status.write_text(
        json.dumps(_status(ledger, prefix), sort_keys=True), encoding="utf-8"
    )
    return status, ledger


def _status(ledger: Path, prefix: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "awaiting_resolution",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "source_strategy_id": (
                "eth_breakout_precompression_pullback_bidirectional_v1"
            ),
            "candidate_strategy_id": (
                "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward"
            ),
            "symbol": "ETH",
            "source_run_id": _RUN,
            "profile_fingerprint": _PROFILE,
            "compatible_run_ids": [_RUN],
            "taker_fee_rate": 0.00045,
        },
        "identity": {"profile_fingerprint": _PROFILE, "source_run_id": _RUN},
        "summary": {
            "pending": 1,
            "resolved": 0,
            "technical_incomplete": 0,
            "selected_non_overlapping": 1,
        },
        "latest_attempts": [_attempt()],
        "latest_executions": [],
        "source_evidence": {
            "ledger": {
                "path": str(ledger),
                "stable_bytes": len(prefix),
                "sha256": sha256(prefix).hexdigest(),
            }
        },
    }


def _attempt() -> dict[str, object]:
    return {
        "candidate_strategy_id": (
            "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward"
        ),
        "source_run_id": _RUN,
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "side": "long",
        "decision_time_ms": 100,
        "status": "exit_pending",
        "entry_time_ms": 10_000,
        "entry_price": 100.0,
        "entry_notional_usd": 750.0,
        "position_quantity": 7.5,
        "current_exit_time_ms": 250_000,
        "current_exit_price": 100.2,
        "current_gross_return_bps": 20.0,
        "current_fee_bps": 9.009,
        "current_funding_bps": 0.0,
        "current_net_return_bps": 10.991,
    }


def _candle_row(
    timestamp_ms: int,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
) -> dict[str, object]:
    return {
        "event_type": "market_candles",
        "run_id": _RUN,
        "profile_fingerprint": _PROFILE,
        "execution_authority": "none",
        "payload": {
            "timeframe": "1m",
            "bars": {
                "ETH": [
                    {
                        "timestamp_ms": timestamp_ms,
                        "open": close,
                        "high": close if high is None else high,
                        "low": close if low is None else low,
                        "close": close,
                        "volume": 1.0,
                    }
                ]
            },
        },
    }


def _history() -> EthExitResearchContext:
    return EthExitResearchContext(
        payload={
            "rejected_profit_locks": [
                "profit_a25_floor15_trail10",
                "profit_a40_floor15_trail20",
                "profit_a60_floor15_trail30",
            ]
        },
        evidence={"journal": {"sha256": "a" * 64}},
    )


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
