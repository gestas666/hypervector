"""Report-only Hypervelocity peak-protection observer tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.paper.book import BookLevel, BookSnapshot
from hypervector.paper.peak_protection_observer import (
    PEAK_OBSERVER_CANDIDATE_ID,
    PEAK_OBSERVER_SCHEMA,
    PeakObserverConfig,
    PeakProtectionObserver,
)
from hypervector.paper.peak_observer_persistence import (
    PeakObserverRestoreError,
    load_peak_observer_state,
)

BASE = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def _config() -> PeakObserverConfig:
    """Return the frozen report-only source sensitivity."""
    return PeakObserverConfig(
        mode="observe",
        candidate_id=PEAK_OBSERVER_CANDIDATE_ID,
        activation_margin_pct=7.0,
        lock_ratio=0.55,
        minimum_stop_move_fraction=0.0005,
        update_cooldown_seconds=60.0,
        sample_interval_seconds=5.0,
        execution_authority="none",
    )


def _ts(seconds: float) -> str:
    """Return one deterministic UTC observer timestamp."""
    return (BASE + timedelta(seconds=seconds)).isoformat()


def _book(seconds: float, *, bid: float, ask: float) -> BookSnapshot:
    """Return a complete deterministic adverse-BBO source."""
    timestamp_ms = (BASE + timedelta(seconds=seconds)).timestamp() * 1_000.0
    return BookSnapshot(
        symbol="BTC",
        bids=(BookLevel(bid, 2.0),),
        asks=(BookLevel(ask, 2.0),),
        ts_recv_ms=timestamp_ms,
        ts_exchange_ms=timestamp_ms,
        source="hyperliquid_ws_l2",
    )


def _observer() -> PeakProtectionObserver:
    """Return the frozen observer with Hyperliquid base-tier exit friction."""
    return PeakProtectionObserver(
        config=_config(),
        leverage=40.0,
        taker_fee_rate=0.00045,
    )


def test_peak_observer_config_exposes_frozen_report_only_contract() -> None:
    config = _config()

    assert config.telemetry() == {
        "schema": PEAK_OBSERVER_SCHEMA,
        "mode": "observe",
        "candidate_id": "source_peak_activation7_v1",
        "activation_margin_pct": 7.0,
        "lock_ratio": 0.55,
        "minimum_stop_move_fraction": 0.0005,
        "update_cooldown_seconds": 60.0,
        "sample_interval_seconds": 5.0,
        "execution_authority": "none",
        "report_only": True,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "execute", "mode"),
        ("candidate_id", "threshold_sweep", "candidate_id"),
        ("activation_margin_pct", 6.0, "activation_margin_pct"),
        ("lock_ratio", 0.6, "lock_ratio"),
        ("minimum_stop_move_fraction", 0.001, "minimum_stop_move_fraction"),
        ("update_cooldown_seconds", 30.0, "update_cooldown_seconds"),
        ("sample_interval_seconds", 1.0, "sample_interval_seconds"),
        ("execution_authority", "shadow", "execution_authority"),
    ],
)
def test_peak_observer_config_rejects_unfrozen_or_executable_values(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_config(), **{field: value})


def test_long_observer_arms_and_prices_hypothetical_exit_at_bid() -> None:
    observer = _observer()

    started = observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )
    armed = observer.observe_mark(
        mark_price=100.175,
        observed_at=_ts(5),
        book=_book(5, bid=100.17, ask=100.18),
        evidence_fresh=True,
    )
    exited = observer.observe_mark(
        mark_price=100.05,
        observed_at=_ts(10),
        book=_book(10, bid=100.04, ask=100.05),
        evidence_fresh=True,
    )

    assert [event["action"] for event in started] == ["peak_observer_position_start"]
    assert [event["action"] for event in armed] == ["peak_observer_armed"]
    assert armed[0]["peak_margin_pct"] == pytest.approx(7.0)
    assert armed[0]["locked_margin_pct"] == pytest.approx(3.85)
    assert armed[0]["hypothetical_stop_price"] == pytest.approx(100.09625)
    assert [event["action"] for event in exited] == ["peak_observer_would_exit"]
    assert exited[0]["hypothetical_exit_price"] == pytest.approx(100.04)
    assert exited[0]["hypothetical_exit_fee_usd"] == pytest.approx(100.04 * 0.00045)
    assert exited[0]["execution_authority"] == "none"
    assert exited[0]["submitted"] is False
    assert exited[0]["place_attempted"] is False


def test_short_observer_uses_side_aware_stop_and_adverse_ask() -> None:
    observer = _observer()
    observer.sync_position(
        quantity=-2.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )

    armed = observer.observe_mark(
        mark_price=99.825,
        observed_at=_ts(5),
        book=_book(5, bid=99.82, ask=99.83),
        evidence_fresh=True,
    )
    exited = observer.observe_mark(
        mark_price=99.95,
        observed_at=_ts(10),
        book=_book(10, bid=99.95, ask=99.96),
        evidence_fresh=True,
    )

    assert armed[0]["hypothetical_stop_price"] == pytest.approx(99.90375)
    assert exited[0]["hypothetical_exit_price"] == pytest.approx(99.96)
    assert exited[0]["hypothetical_exit_fee_usd"] == pytest.approx(
        2.0 * 99.96 * 0.00045
    )


def test_observer_retains_peak_until_update_constraints_are_met() -> None:
    observer = _observer()
    observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )
    observer.observe_mark(
        mark_price=100.175,
        observed_at=_ts(5),
        book=_book(5, bid=100.17, ask=100.18),
        evidence_fresh=True,
    )

    too_small = observer.observe_mark(
        mark_price=100.25,
        observed_at=_ts(66),
        book=_book(66, bid=100.24, ask=100.25),
        evidence_fresh=True,
    )
    updated = observer.observe_mark(
        mark_price=100.375,
        observed_at=_ts(71),
        book=_book(71, bid=100.37, ask=100.38),
        evidence_fresh=True,
    )
    cooldown = observer.observe_mark(
        mark_price=100.5,
        observed_at=_ts(76),
        book=_book(76, bid=100.49, ask=100.5),
        evidence_fresh=True,
    )
    retained = observer.observe_mark(
        mark_price=100.4,
        observed_at=_ts(132),
        book=_book(132, bid=100.39, ask=100.4),
        evidence_fresh=True,
    )

    assert too_small == ()
    assert [event["action"] for event in updated] == ["peak_observer_updated"]
    assert updated[0]["peak_margin_pct"] == pytest.approx(15.0)
    assert cooldown == ()
    assert observer.state is not None
    assert observer.state.peak_margin_pct == pytest.approx(20.0)
    assert [event["action"] for event in retained] == ["peak_observer_updated"]
    assert retained[0]["peak_margin_pct"] == pytest.approx(20.0)
    assert retained[0]["hypothetical_stop_price"] == pytest.approx(100.275)


def test_observer_does_not_sample_between_source_cadence_ticks() -> None:
    observer = _observer()
    observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )
    observer.observe_mark(
        mark_price=100.175,
        observed_at=_ts(5),
        book=_book(5, bid=100.17, ask=100.18),
        evidence_fresh=True,
    )

    skipped = observer.observe_mark(
        mark_price=100.0,
        observed_at=_ts(9),
        book=_book(9, bid=99.99, ask=100.0),
        evidence_fresh=True,
    )
    sampled = observer.observe_mark(
        mark_price=100.0,
        observed_at=_ts(10),
        book=_book(10, bid=99.99, ask=100.0),
        evidence_fresh=True,
    )

    assert skipped == ()
    assert [event["action"] for event in sampled] == ["peak_observer_would_exit"]


def test_stale_trigger_is_unpriced_and_marks_coverage_incomplete() -> None:
    observer = _observer()
    observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )
    observer.observe_mark(
        mark_price=100.175,
        observed_at=_ts(5),
        book=_book(5, bid=100.17, ask=100.18),
        evidence_fresh=True,
    )

    unpriced = observer.observe_mark(
        mark_price=100.05,
        observed_at=_ts(10),
        book=None,
        evidence_fresh=False,
    )
    duplicate = observer.observe_mark(
        mark_price=100.04,
        observed_at=_ts(15),
        book=None,
        evidence_fresh=False,
    )
    priced = observer.observe_mark(
        mark_price=100.03,
        observed_at=_ts(20),
        book=_book(20, bid=100.02, ask=100.03),
        evidence_fresh=True,
    )

    assert [event["action"] for event in unpriced] == ["peak_observer_trigger_unpriced"]
    assert unpriced[0]["trigger_evidence_status"] == "stale_or_missing_book"
    assert unpriced[0]["coverage_complete_since_entry"] is False
    assert duplicate == ()
    assert [event["action"] for event in priced] == ["peak_observer_would_exit"]
    assert priced[0]["coverage_complete_since_entry"] is False


def test_actual_flat_position_ends_observation_without_claiming_execution() -> None:
    observer = _observer()
    observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )

    ended = observer.sync_position(
        quantity=0.0,
        average_price=None,
        observed_at=_ts(30),
        coverage_complete_since_entry=True,
    )

    assert [event["action"] for event in ended] == ["peak_observer_position_end"]
    assert ended[0]["observer_active"] is False
    assert ended[0]["execution_authority"] == "none"
    assert observer.state is None


def test_peak_observer_restores_latest_complete_candidate_state(
    tmp_path: Path,
) -> None:
    observer = _observer()
    observer.sync_position(
        quantity=-2.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )
    armed = observer.observe_mark(
        mark_price=99.825,
        observed_at=_ts(5),
        book=_book(5, bid=99.82, ask=99.83),
        evidence_fresh=True,
    )[0]
    path = tmp_path / "decisions.jsonl"
    rows = [
        {**armed, "run_id": "other", "candidate_id": "other-candidate"},
        {**armed, "run_id": "run-1"},
    ]
    path.write_text(
        "".join(f"{json.dumps(row)}\n" for row in rows),
        encoding="utf-8",
    )

    restored = load_peak_observer_state(
        path,
        run_id="run-1",
        candidate_id=PEAK_OBSERVER_CANDIDATE_ID,
    )

    assert restored == observer.state


def test_peak_observer_restore_returns_flat_after_position_end(
    tmp_path: Path,
) -> None:
    observer = _observer()
    started = observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(0),
        coverage_complete_since_entry=True,
    )[0]
    ended = observer.sync_position(
        quantity=0.0,
        average_price=None,
        observed_at=_ts(10),
        coverage_complete_since_entry=True,
    )[0]
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        f"{json.dumps({**started, 'run_id': 'run-1'})}\n"
        f"{json.dumps({**ended, 'run_id': 'run-1'})}\n",
        encoding="utf-8",
    )

    assert (
        load_peak_observer_state(
            path,
            run_id="run-1",
            candidate_id=PEAK_OBSERVER_CANDIDATE_ID,
        )
        is None
    )


def test_peak_observer_restore_rejects_malformed_matching_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "action": "peak_observer_armed",
                "observer_schema": PEAK_OBSERVER_SCHEMA,
                "candidate_id": PEAK_OBSERVER_CANDIDATE_ID,
                "observer_active": True,
                "position_direction": "long",
                "position_quantity": "not-a-number",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PeakObserverRestoreError, match="position_quantity"):
        load_peak_observer_state(
            path,
            run_id="run-1",
            candidate_id=PEAK_OBSERVER_CANDIDATE_ID,
        )


def test_observer_started_mid_position_marks_coverage_incomplete() -> None:
    observer = _observer()

    started = observer.sync_position(
        quantity=1.0,
        average_price=100.0,
        observed_at=_ts(30),
        coverage_complete_since_entry=False,
    )

    assert started[0]["coverage_complete_since_entry"] is False
