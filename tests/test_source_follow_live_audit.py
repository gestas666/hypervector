"""Report-only audit of event-sourced BTC source-follow live runs."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.source_follow_live_audit import (
    audit_source_follow_live_run,
)
from source_follow_live_audit_fixtures import candle as _candle
from source_follow_live_audit_fixtures import event as _event
from source_follow_live_audit_fixtures import identity as _identity


def test_audit_selects_latest_or_explicit_identified_run() -> None:
    """Run selection must not mix evidence from adjacent ledger sessions."""
    rows = [
        _identity("run-a", 1, "profile-a"),
        _candle("run-a", 2, profile_id="profile-a"),
        _identity("run-b", 3, "profile-b"),
        _candle("run-b", 4, profile_id="profile-b"),
    ]

    latest = audit_source_follow_live_run(rows)
    explicit = audit_source_follow_live_run(rows, run_id="run-a")

    assert latest["run"]["run_id"] == "run-b"
    assert latest["run"]["profile_id"] == "profile-b"
    assert latest["run"]["row_count"] == 2
    assert explicit["run"]["run_id"] == "run-a"
    assert explicit["run"]["profile_id"] == "profile-a"
    assert explicit["run"]["row_count"] == 2


def test_audit_rejects_missing_identity_and_mixed_profile() -> None:
    """A live audit cannot infer identity or combine incompatible profiles."""
    with pytest.raises(ValueError, match="configuration_identity"):
        audit_source_follow_live_run([_candle("run-a", 1)])

    mixed = [
        _identity("run-a", 1, "profile-a"),
        _event("run-a", 2, "state_transition", {"state": "FLAT"}, profile_id="other"),
    ]
    with pytest.raises(ValueError, match="mixed profile identity"):
        audit_source_follow_live_run(mixed)


def test_audit_rejects_invalid_or_unaligned_backend_candle() -> None:
    """Malformed backend OHLCV cannot become success-shaped audit evidence."""
    invalid = _candle("run-a", 2)
    invalid_payload = invalid["payload"]
    assert isinstance(invalid_payload, dict)
    invalid_payload["high"] = 98.0
    rows = [_identity("run-a", 1, "source-bidirectional"), invalid]
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        audit_source_follow_live_run(rows)

    unaligned = deepcopy(_candle("run-a", 2))
    unaligned_payload = unaligned["payload"]
    assert isinstance(unaligned_payload, dict)
    unaligned_payload["feed_ts"] = "2026-07-31T20:01:00+00:00"
    rows = [_identity("run-a", 1, "source-bidirectional"), unaligned]
    with pytest.raises(ValueError, match="five-minute aligned"):
        audit_source_follow_live_run(rows)


def test_audit_reports_history_authority_violations_without_hiding_rows() -> None:
    """Warm history stays visible even when a row violates its no-entry contract."""
    clean = _candle("run-a", 2)
    violating = _candle(
        "run-a",
        3,
        feed_ts="2026-07-31T20:05:00+00:00",
    )
    payload = violating["payload"]
    assert isinstance(payload, dict)
    payload["entry_allowed"] = True
    payload["short_entry"] = True
    payload["decision_action"] = "enter_short"

    report = audit_source_follow_live_run(
        [_identity("run-a", 1, "source-bidirectional"), clean, violating]
    )

    assert report["history"]["rows"] == 2
    assert report["history"]["all_non_executable"] is False
    assert report["history"]["authority_violation_count"] == 1
    assert report["history"]["authority_violations"] == [
        {
            "sequence": 3,
            "feed_ts": "2026-07-31T20:05:00+00:00",
            "entry_allowed": True,
            "regime_admitted": False,
            "long_entry": False,
            "short_entry": True,
            "decision_action": "enter_short",
        }
    ]
    assert report["history"]["regime_distribution"] == {"RANGE": 2}


def test_audit_summarizes_every_executable_decision_result() -> None:
    """Zero entries and qualified entries remain in the same decision surface."""
    hold = _candle("run-a", 2, event_type="regime_decision")
    hold_payload = hold["payload"]
    assert isinstance(hold_payload, dict)
    hold_payload.update(
        {
            "primary_onset": False,
            "source_event": False,
            "decision_action": "hold",
            "regime_reason": "not_primary_onset",
            "entry_direction": None,
        }
    )
    signal = _candle(
        "run-a",
        3,
        event_type="regime_decision",
        feed_ts="2026-07-31T20:05:00+00:00",
    )
    signal_payload = signal["payload"]
    assert isinstance(signal_payload, dict)
    signal_payload.update(
        {
            "primary_regime": "TREND_DOWN",
            "primary_onset": True,
            "source_event": True,
            "entry_allowed": True,
            "regime_admitted": True,
            "short_entry": True,
            "entry_direction": "short",
            "decision_action": "enter_short",
            "regime_reason": "source_follow_entry_pulse",
        }
    )

    report = audit_source_follow_live_run(
        [_identity("run-a", 1, "source-bidirectional"), hold, signal]
    )

    assert report["decisions"] == {
        "rows": 2,
        "primary_regime_distribution": {"RANGE": 1, "TREND_DOWN": 1},
        "decision_action_distribution": {"enter_short": 1, "hold": 1},
        "exclusion_reason_distribution": {
            "not_primary_onset": 1,
            "source_follow_entry_pulse": 1,
        },
        "direction_distribution": {"none": 1, "short": 1},
        "primary_onsets": 1,
        "source_events": 1,
        "eligible_signals": 1,
    }


def test_audit_measures_decision_latency_against_entry_pulse() -> None:
    """Late source decisions remain visible as timing failures, not silent holds."""
    timely = _candle("run-a", 2, event_type="regime_decision")
    timely["observed_at_utc"] = "2026-07-31T20:05:07+00:00"
    timely_payload = timely["payload"]
    assert isinstance(timely_payload, dict)
    timely_payload.update(
        {
            "available_at_utc": "2026-07-31T20:05:00+00:00",
            "entry_pulse_expires_at_utc": "2026-07-31T20:06:00+00:00",
            "source_event": False,
        }
    )
    late = _candle(
        "run-a",
        3,
        event_type="regime_decision",
        feed_ts="2026-07-31T20:05:00+00:00",
    )
    late["observed_at_utc"] = "2026-07-31T20:11:05+00:00"
    late_payload = late["payload"]
    assert isinstance(late_payload, dict)
    late_payload.update(
        {
            "available_at_utc": "2026-07-31T20:10:00+00:00",
            "entry_pulse_expires_at_utc": "2026-07-31T20:11:00+00:00",
            "source_event": True,
            "regime_reason": "entry_pulse_expired",
        }
    )

    report = audit_source_follow_live_run(
        [_identity("run-a", 1, "source-bidirectional"), timely, late]
    )

    assert report["decision_latency"] == {
        "decision_rows": 2,
        "measured_rows": 2,
        "rows_missing_timestamps": 0,
        "entry_pulse_seconds": 60.0,
        "minimum_seconds": 7.0,
        "median_seconds": 36.0,
        "maximum_seconds": 65.0,
        "at_or_after_entry_pulse_rows": 1,
        "source_events_at_or_after_entry_pulse_rows": 1,
        "late_sequences": [3],
    }


def test_audit_separates_raw_regime_from_confirmed_state() -> None:
    """Raw classification and hysteresis output must be independently auditable."""
    decision = _candle("run-a", 2, event_type="regime_decision")
    payload = decision["payload"]
    assert isinstance(payload, dict)
    payload["primary_regime"] = "RANGE"
    payload["regime_diagnostics"] = {
        "authority": "telemetry_only",
        "raw_primary": "TREND_DOWN",
        "raw_secondary": None,
        "raw_confidence": 0.8,
        "confirmed_primary": "RANGE",
        "state_filtered": True,
        "adx": 12.5,
        "adx_percentile_rank": 0.51,
        "adx_range_percentile_threshold": 0.4,
        "adx_weak_percentile_threshold": 0.5,
        "ema_alignment": "bearish",
        "rsi": 48.0,
        "volume_ratio": 0.8,
        "range_break_up": False,
        "range_break_down": False,
    }

    report = audit_source_follow_live_run(
        [_identity("run-a", 1, "source-bidirectional"), decision]
    )

    assert report["regime_diagnostics"] == {
        "decision_rows": 1,
        "rows_with_diagnostics": 1,
        "rows_missing_diagnostics": 0,
        "raw_primary_distribution": {"TREND_DOWN": 1},
        "raw_confirmed_distribution": {"TREND_DOWN->RANGE": 1},
        "state_filtered_rows": 1,
        "raw_range_rule_rows": 0,
    }


def test_audit_projects_persisted_lifecycle_without_deriving_state() -> None:
    """The audit reports venue/backend facts and does not calculate substitutes."""
    rows = [
        _identity("run-a", 1, "source-bidirectional"),
        _event(
            "run-a",
            2,
            "reconciliation",
            {
                "account_value_usd": 153.61,
                "withdrawable_usd": 100.0,
                "open_order_ids": [101],
                "open_orders": [{"oid": 101, "reduce_only": False}],
            },
        ),
        _event(
            "run-a",
            3,
            "position",
            {"size_signed": -0.025, "entry_price": 64_000.0},
        ),
        _event(
            "run-a",
            4,
            "state_transition",
            {
                "state": "ENTRY_PENDING",
                "entry_oid": 101,
                "target_oid": None,
                "position_size_signed": 0.0,
                "last_fault": None,
            },
        ),
        _event("run-a", 5, "order_intent", {"operation": "entry"}),
        _event("run-a", 6, "order_acknowledgement", {"oid": 101}),
        _event("run-a", 7, "target_order", {"oid": 202}),
        _event("run-a", 8, "fill", {"oid": 101, "price": 64_000.0}),
        _event("run-a", 9, "funding", {"usdc_delta": -0.01}),
        _event("run-a", 10, "close", {"reason": "target"}),
        _event("run-a", 11, "fault", {"reason": "test fault"}),
    ]

    report = audit_source_follow_live_run(rows)

    assert report["lifecycle"]["event_counts"] == {
        "closes": 1,
        "faults": 1,
        "fills": 1,
        "funding": 1,
        "order_acknowledgements": 1,
        "order_intents": 1,
        "target_orders": 1,
    }
    assert report["lifecycle"]["latest_state"] == rows[3]["payload"]
    assert report["lifecycle"]["latest_reconciliation"] == rows[1]["payload"]
    assert report["lifecycle"]["latest_position"] == rows[2]["payload"]
    assert report["lifecycle"]["faults"] == [
        {
            "sequence": 11,
            "observed_at_utc": "2026-07-31T20:11:00+00:00",
            "reason": "test fault",
        }
    ]


def test_audit_leaves_missing_lifecycle_facts_unavailable() -> None:
    """No persisted venue observation means unavailable, not a synthetic flat state."""
    report = audit_source_follow_live_run(
        [_identity("run-a", 1, "source-bidirectional")]
    )

    assert report["lifecycle"]["latest_state"] is None
    assert report["lifecycle"]["latest_reconciliation"] is None
    assert report["lifecycle"]["latest_position"] is None
