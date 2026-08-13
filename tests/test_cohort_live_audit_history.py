"""Point-in-time evidence selection tests for cohort live audits."""

from __future__ import annotations

from datetime import UTC, datetime

from hypervector.research.cohort_live_audit_history import (
    select_all_time_asset_evidence,
    select_asset_evidence,
)


def test_historical_run_excludes_compatible_rows_observed_after_cutoff() -> None:
    """A past-window audit cannot see fills or lifecycles from a later restart."""
    rows = [
        _row(1, "run-a", "2026-08-03T10:00:00+00:00", "configuration_identity"),
        _row(2, "run-a", "2026-08-03T10:05:00+00:00", "state_transition"),
        _row(3, "run-b", "2026-08-03T11:00:00+00:00", "configuration_identity"),
        _row(4, "run-b", "2026-08-03T11:05:00+00:00", "order_acknowledgement"),
    ]

    current, history = select_asset_evidence(
        {"BTC": rows},
        ("BTC",),
        "run-a",
        as_of=datetime(2026, 8, 3, 10, 10, tzinfo=UTC),
    )

    assert [row["sequence"] for row in current["BTC"]] == [1, 2]
    assert [row["sequence"] for row in history["BTC"]] == [1, 2]


def test_current_run_excludes_asset_rows_observed_after_cohort_cutoff() -> None:
    """A live audit cannot combine a cohort prefix with later asset events."""
    rows = [
        _row(1, "run-a", "2026-08-03T10:00:00+00:00", "configuration_identity"),
        _row(2, "run-a", "2026-08-03T10:05:00+00:00", "state_transition"),
        _row(3, "run-a", "2026-08-03T10:11:00+00:00", "fill"),
        _row(4, "run-a", "2026-08-03T10:12:00+00:00", "state_transition"),
    ]
    cutoff = datetime(2026, 8, 3, 10, 10, tzinfo=UTC)

    current, history = select_asset_evidence(
        {"BTC": rows},
        ("BTC",),
        "run-a",
        as_of=cutoff,
    )
    all_time = select_all_time_asset_evidence(
        {"BTC": rows},
        ("BTC",),
        "run-a",
        as_of=cutoff,
    )

    assert [row["sequence"] for row in current["BTC"]] == [1, 2]
    assert [row["sequence"] for row in history["BTC"]] == [1, 2]
    assert [row["sequence"] for row in all_time["BTC"]] == [1, 2]


def test_all_time_history_retains_prior_live_profiles_before_cutoff() -> None:
    """User-facing history must not disappear when the runtime profile changes."""
    prior = _row(1, "run-a", "2026-08-03T10:00:00+00:00", "configuration_identity")
    prior["profile_fingerprint"] = "prior-profile"
    prior["run_fingerprint"] = "prior-run-fingerprint"
    current = _row(2, "run-b", "2026-08-03T11:00:00+00:00", "configuration_identity")
    future = _row(3, "run-c", "2026-08-03T12:00:00+00:00", "fill")
    unarmed = _row(4, "run-d", "2026-08-03T10:30:00+00:00", "fill")
    unarmed["live_armed"] = False

    history = select_all_time_asset_evidence(
        {"BTC": [prior, current, future, unarmed]},
        ("BTC",),
        "run-b",
        as_of=datetime(2026, 8, 3, 11, 30, tzinfo=UTC),
    )

    assert [row["run_id"] for row in history["BTC"]] == ["run-a", "run-b"]


def _row(
    sequence: int,
    run_id: str,
    observed_at_utc: str,
    event_type: str,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "run_id": run_id,
        "observed_at_utc": observed_at_utc,
        "event_type": event_type,
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "profile",
        "profile_fingerprint": "profile-fingerprint",
        "run_fingerprint": "run-fingerprint",
        "payload": {"symbol": "BTC"},
    }
