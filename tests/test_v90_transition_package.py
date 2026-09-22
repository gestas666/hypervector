"""Validate the exact pending V90 package without granting execution authority."""

import json
from pathlib import Path
import plistlib


from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
    _validate_profile_identity,
    _validate_retirements,
    _verify_recommendation_evidence,
    _verify_rollback,
)
from hypervector.live.cohort_profit_lock_history import profit_lock_history_limits
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

ROOT = Path("docs/proposals/v90-supervisor-20260920/v90-launchagents")
PROFILE = Path(
    "configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml"
)
BASELINE = Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml")


def test_signed_approval_binds_the_armed_candidate_and_records_the_operator() -> None:
    """The approval was signed 2026-09-22 with the operator's verbatim words."""
    previous = load_multi_asset_live_config(BASELINE, mode="observe")
    candidate = load_multi_asset_live_config(PROFILE, mode="observe")
    path = candidate.transition_approval
    assert path is not None
    document = json.loads(path.read_bytes())
    assert document["approval_status"] == "approved_for_live_transition"
    assert document["approved_by"] == "operator_in_conversation"
    assert document["operator_approval"] == "approave everything for v90 to go live now"
    assert document["approved_at_utc"].startswith("2026-09-22T")
    assert document["execution_authority"] == "none"
    assert document["candidate_profile"]["profile_fingerprint"] == (
        candidate.profile_fingerprint
    )
    assert any(
        scope.startswith("post_approval_correction_20260922")
        for scope in document["change_scopes"]
    )
    _validate_profile_identity(document, previous, candidate)
    _verify_recommendation_evidence(document, path.parent)
    _verify_rollback(document, path.parent, previous)
    _validate_retirements(document, previous, candidate)
    result = validate_profile_change_approval(previous, candidate, path)
    assert result["state"] == "approved_profile_change"


def test_prepared_services_use_candidate_and_do_not_adopt_another_owner() -> None:
    """Backend and checkpoint definitions name the same exact future profile."""
    for kind in ("supervise", "checkpoint"):
        document = plistlib.loads(
            (ROOT / f"local.hypervector.cohort.{kind}.plist").read_bytes()
        )
        args = document["ProgramArguments"]
        assert args[args.index("--config") + 1] == str(PROFILE)
        assert document["WorkingDirectory"] == "/Users/gestas/Prototypes/hypervector"
        assert "--run-id" not in args
        if kind == "supervise":
            assert "--adopt" not in args
            assert "--enabled" in args and "--i-accept-live-risk" in args
        else:
            assert "--follow-latest-run" in args


def test_option_b_candidate_requires_no_profit_lock_history() -> None:
    """With every hourly route unlocked, no symbol needs the full-day lock history.

    Option B of docs/reviews/2026-09-21-v90-profit-lock-exit-review.md runs the
    unlocked identity; the history requirement exists only for lock-enabled
    symbols, so an empty mapping is the correct, deliberate result.
    """
    candidate = load_multi_asset_live_config(PROFILE, mode="observe")
    assert profit_lock_history_limits(candidate.providers) == {}
    assert all(
        provider.execution.profit_lock_policy == "none"
        for provider in candidate.providers
        if provider.execution_symbols
    )
