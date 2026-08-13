"""Armed cohort run selection tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_live_run_selection import (
    select_compatible_armed_live_runs,
)


def test_compatible_selection_accumulates_only_the_anchor_profile() -> None:
    """Matching restarts append while a different configuration remains excluded."""
    records = [
        _row("configuration_identity", "run-a", "profile-a"),
        _row("intent_routing", "run-a", "profile-a"),
        _row("configuration_identity", "run-b", "profile-b"),
        _row("intent_routing", "run-b", "profile-b"),
        _row("configuration_identity", "run-c", "profile-a"),
        _row("intent_routing", "run-c", "profile-a"),
    ]

    selected, identities = select_compatible_armed_live_runs(
        records,
        profile_fingerprint="profile-a",
        required_run_id="run-a",
    )

    assert {row["run_id"] for row in selected} == {"run-a", "run-c"}
    assert [row["run_id"] for row in identities] == ["run-a", "run-c"]


def test_compatible_selection_rejects_an_incompatible_required_run() -> None:
    """An operator anchor cannot silently resolve to a different profile."""
    records = [_row("configuration_identity", "run-b", "profile-b")]

    with pytest.raises(ValueError, match="required armed run"):
        select_compatible_armed_live_runs(
            records,
            profile_fingerprint="profile-a",
            required_run_id="run-b",
        )


def _row(event_type: str, source_run_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": source_run_id,
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_fingerprint": fingerprint,
        "payload": {
            "strategy_name": "multi_asset_bidirectional_cohort",
            "profile_fingerprint": fingerprint,
        },
    }
