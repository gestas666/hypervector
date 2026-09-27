"""V95 is V94 minus HYPE and xyz:SPCX, and its approvals wait for the operator.

Review item B2: remove the HYPE and xyz:SPCX assets, their two watch-only
providers and every override table naming them. Every value that remains must
equal V94's. Neither provider had an executable scope in V94, so the change
retires no execution scope.

Both approval records (V94 -> V95 and the pre-authored V95 -> V94 rollback) are
committed as ``pending_operator_approval`` with empty operator fields, so every
gate refuses them. Once the operator approves, record the operator's exact words
in both records and pin them here in place of the pending assertions, as
tests/test_v93_to_v91_rollback_pair.py does.
"""

from __future__ import annotations

from collections.abc import Iterator
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tomllib

import pytest

import cohort_rollback_profile as rollback
import cohort_runtime_validation_check as check
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

REPOSITORY = Path(__file__).resolve().parents[1]
V94 = "configs/multi_asset_growth_first_5000_review_actions_v94.toml"
V95 = "configs/multi_asset_growth_first_5000_review_fixes_v95.toml"
APPROVAL = "docs/live-approvals/v94-to-v95-review-fixes-20260927-v1.json"
ROLLBACK = "configs/v95-to-v94-rollback-20260927-v1.toml"
ROLLBACK_APPROVAL = "docs/live-approvals/v95-to-v94-rollback-20260927-v1.json"
GENERATOR = "scripts/cohort_rollback_profile.py"
V94_ID = "multi_asset_growth_first_5000_review_actions_v94"
V95_ID = "multi_asset_growth_first_5000_review_fixes_v95"
V94_FINGERPRINT = "930117e9ac0f4bb91fc66631666f47eb68a5d66bd8928684d8792f63122b3fd1"
V95_FINGERPRINT = "dd779cce74568e4ba6963d1a19810a7fbcaa7f4279e40f45be83f12286339420"
ROLLBACK_FINGERPRINT = (
    "5fe5a9de14b4ae7b7ab7e53cea7dd6c8bc6a2341f851b2d76f5b0e158a6c7beb"
)
REVIEW_EQUITY = 4_831.43

BTC_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2"
ETH_RANGE = "eth_range_onset_long_dual_mtf_v2"
DONCHIAN = "hourly_donchian_20_10_atr20_strong_short_v1"
HYPE_ALIGN = "hype_breakout_compression_alignment_bidirectional_v2"
SPCX_BAND20 = "hourly_band20_reentry_atr20_bidirectional_v1"
REMOVED_SYMBOLS = frozenset({"HYPE", "xyz:SPCX"})
REMOVED_PROVIDERS = frozenset({HYPE_ALIGN, SPCX_BAND20})
KEPT_SYMBOLS = ("BTC", "ETH", "SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
V93_REVIEW = "docs/reviews/2026-09-24-v93-full-review.md"
V94_PLAN = "docs/plans/2026-09-24-v94-review-actions.md"
V95_REVIEW = "docs/reviews/2026-09-27-v94-review-and-swing-research.md"
HANDOFF = "HANDOFF.md"
# Every armed start re-hashes the cited evidence, so an approval may cite only
# files that stay frozen until the transition completes. HANDOFF.md is a running
# ops log: an edit between approval and the V95 start would refuse that start
# after the V94 drain has already flattened the book.
FORWARD_EVIDENCE = (V95_REVIEW, V93_REVIEW, V94_PLAN, ROLLBACK)
ROLLBACK_EVIDENCE = (V94, V93_REVIEW, V94_PLAN)
PENDING = "pending_operator_approval"
# Test-only stand-ins for the operator fields; never copied into the repository.
PLACEHOLDER = {
    "approval_status": "approved_for_live_transition",
    "approved_at_utc": "2026-09-27T00:00:00+00:00",
    "approved_by": "test_placeholder_not_operator",
    "operator_approval": "test placeholder, not operator approval",
}


def _load(path: str | Path, mode: str = "observe") -> MultiAssetLiveConfig:
    armed = mode == "live"
    return load_multi_asset_live_config(
        path, mode=mode, enabled=armed, accepts_live_risk=armed
    )


def _raw(path: str) -> dict[str, object]:
    return tomllib.loads((REPOSITORY / path).read_text(encoding="utf-8"))


def _document(path: str) -> dict[str, object]:
    return json.loads((REPOSITORY / path).read_text(encoding="utf-8"))


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _strings(value: object) -> Iterator[str]:
    """Yield every key and text value of a parsed profile, recursively."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _mirror(root: Path, approval: str, *paths: str) -> None:
    """Copy one approval, what it cites and the given files into ``root``."""
    document = _document(approval)
    base = Path(approval).parent
    cited = [
        os.path.normpath(base / str(row["path"]))
        for row in document["recommendation_evidence"]
    ]
    cited.append(os.path.normpath(base / str(document["rollback"]["config_path"])))
    for relative in dict.fromkeys((approval, *paths, *cited)):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / relative, target)


def _rewrite(root: Path, approval: str, **fields: object) -> Path:
    path = root / approval
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(fields)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def test_v95_identity_is_pinned_and_v94_is_unchanged() -> None:
    previous = _load(REPOSITORY / V94)
    candidate = _load(REPOSITORY / V95)
    assert previous.profile_fingerprint == V94_FINGERPRINT
    assert candidate.profile_fingerprint == V95_FINGERPRINT
    assert _load(REPOSITORY / V95, "live").profile_fingerprint == V95_FINGERPRINT
    assert candidate.profile_id == V95_ID
    assert candidate.transition_approval == Path(APPROVAL)
    assert not candidate.enabled and not candidate.accepts_live_risk


def test_v95_keeps_exactly_six_assets_and_three_providers() -> None:
    candidate = _load(REPOSITORY / V95)
    assert candidate.symbols == KEPT_SYMBOLS
    assert [provider.strategy_id for provider in candidate.providers] == [
        BTC_SWEEP,
        ETH_RANGE,
        DONCHIAN,
    ]
    assert candidate.maximum_positions == 8


def test_no_value_or_override_table_names_a_removed_asset_or_provider() -> None:
    observed = set(_strings(_raw(V95)))
    assert observed.isdisjoint(REMOVED_SYMBOLS | REMOVED_PROVIDERS)
    for provider in _load(REPOSITORY / V95).providers:
        named = {
            *provider.symbols,
            *(symbol for symbol, _ in provider.execution_side_overrides),
            *(symbol for symbol, _ in provider.sizing_overrides),
            *(symbol for symbol, _, _ in provider.directional_sizing_overrides),
            *(symbol for symbol, _ in provider.stop_bps_overrides),
        }
        assert named.isdisjoint(REMOVED_SYMBOLS)


def test_v95_values_are_v94_minus_the_removed_tables() -> None:
    """Byte-for-byte values: only the id, the approval path and removals differ."""
    expected = copy.deepcopy(_raw(V94))
    expected["profile"] = V95_ID
    expected["runtime"]["transition_approval"] = APPROVAL
    expected["assets"] = [
        row for row in expected["assets"] if row["symbol"] not in REMOVED_SYMBOLS
    ]
    expected["providers"] = [
        row
        for row in expected["providers"]
        if row["strategy_id"] not in REMOVED_PROVIDERS
    ]
    assert _raw(V95) == expected


def test_kept_routes_load_identical_to_v94() -> None:
    previous = _load(REPOSITORY / V94)
    candidate = _load(REPOSITORY / V95)
    assert tuple(
        replace(asset, parent_profile_id=V94_ID) for asset in candidate.assets
    ) == tuple(
        asset for asset in previous.assets if asset.symbol not in REMOVED_SYMBOLS
    )
    assert candidate.providers == tuple(
        provider
        for provider in previous.providers
        if provider.strategy_id not in REMOVED_PROVIDERS
    )
    assert (
        candidate.executable_provider_directions
        == previous.executable_provider_directions
    )
    assert (
        candidate.network,
        candidate.margin_mode,
        candidate.maximum_positions,
        candidate.cohort_ledger,
        candidate.stop_file,
        candidate.poll_seconds,
        candidate.lookback_days,
    ) == (
        previous.network,
        previous.margin_mode,
        previous.maximum_positions,
        previous.cohort_ledger,
        previous.stop_file,
        previous.poll_seconds,
        previous.lookback_days,
    )


@pytest.mark.parametrize("mode", ["observe", "live"])
def test_live_runner_validation_accepts_v95(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPOSITORY)
    assert check.check(Path(V95), mode=mode) == []


def test_book_level_risk_and_margin_equal_v94() -> None:
    """The removed routes were watch-only, so the book check does not move."""
    previous = check.book_check(REPOSITORY / V94, equity_usd=REVIEW_EQUITY)
    candidate = check.book_check(REPOSITORY / V95, equity_usd=REVIEW_EQUITY)
    assert candidate.problems == ()
    assert candidate.routes == previous.routes
    assert candidate.at_stop_loss_usd == pytest.approx(previous.at_stop_loss_usd)
    assert candidate.margin_usd == pytest.approx(previous.margin_usd)
    assert candidate.at_stop_loss_usd / REVIEW_EQUITY == pytest.approx(
        0.01656, abs=1e-4
    )
    assert candidate.margin_usd / REVIEW_EQUITY == pytest.approx(0.1089, abs=1e-4)


def test_v94_to_v95_approval_binds_the_exact_pair() -> None:
    document = _document(APPROVAL)
    assert document["previous_profile"] == {
        "profile_id": V94_ID,
        "profile_fingerprint": V94_FINGERPRINT,
    }
    assert document["candidate_profile"] == {
        "profile_id": V95_ID,
        "profile_fingerprint": V95_FINGERPRINT,
    }
    assert document["execution_authority"] == "none"
    # The validator requires the rollback config to carry the previous (V94)
    # fingerprint, so it names V94 itself; the startable V95 -> V94 rollback
    # profile is cited as evidence instead.
    assert document["rollback"] == {
        "config_path": f"../../{V94}",
        "profile_fingerprint": V94_FINGERPRINT,
        "sha256": _sha256(REPOSITORY / V94),
    }
    assert {
        "path": f"../../{ROLLBACK}",
        "sha256": _sha256(REPOSITORY / ROLLBACK),
    } in document["recommendation_evidence"]
    assert document["retirements"] == []
    assert any("hype" in scope for scope in document["change_scopes"])
    assert any("spcx" in scope for scope in document["change_scopes"])
    # The unsigned read-only transition preflight still requires the exact
    # venue maximum; only the start probe and the engine preflight relaxed.
    assert (
        "venue_max_leverage_refuses_only_below_requested_leverage_in_start_probe"
        "_and_engine_preflight"
    ) in document["change_scopes"]


@pytest.mark.parametrize(
    ("approval", "expected"),
    [(APPROVAL, FORWARD_EVIDENCE), (ROLLBACK_APPROVAL, ROLLBACK_EVIDENCE)],
)
def test_approvals_cite_only_frozen_evidence(
    approval: str, expected: tuple[str, ...]
) -> None:
    rows = _document(approval)["recommendation_evidence"]
    base = Path(approval).parent
    cited = tuple(os.path.normpath(base / str(row["path"])) for row in rows)
    assert cited == expected
    assert HANDOFF not in cited
    for relative, row in zip(cited, rows, strict=True):
        assert row["sha256"] == _sha256(REPOSITORY / relative)


def test_v94_to_v95_survives_a_handoff_edit_after_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recording the drain in HANDOFF.md must not refuse the V95 start."""
    _mirror(tmp_path, APPROVAL, V95, HANDOFF)
    _rewrite(tmp_path, APPROVAL, **PLACEHOLDER)
    with (tmp_path / HANDOFF).open("a", encoding="utf-8") as handle:
        handle.write("\n- V94 drain archived; V95 armed start next.\n")
    monkeypatch.chdir(tmp_path)
    summary = rollback.dry_run_startup(Path(V94), Path(V95))
    assert (
        summary["startup_profile_change_approval"]["state"] == "approved_profile_change"
    )


@pytest.mark.parametrize("approval", [APPROVAL, ROLLBACK_APPROVAL])
def test_approvals_are_pending_without_operator_words(approval: str) -> None:
    document = _document(approval)
    assert document["approval_status"] == PENDING
    assert document["approved_at_utc"] == ""
    assert document["approved_by"] == ""
    assert document["operator_approval"] == ""


def test_pending_v94_to_v95_approval_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPOSITORY)
    previous = _load(V94)
    candidate = _load(V95, "live")
    with pytest.raises(
        ProfileChangeApprovalError,
        match="approval status is not approved_for_live_transition",
    ):
        validate_profile_change_approval(
            previous, candidate, candidate.transition_approval
        )
    with pytest.raises(ProfileChangeApprovalError, match="approval status"):
        rollback.dry_run_startup(Path(V94), Path(V95))


def test_flipping_the_status_alone_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mirror(tmp_path, APPROVAL, V95)
    _rewrite(tmp_path, APPROVAL, approval_status=PLACEHOLDER["approval_status"])
    monkeypatch.chdir(tmp_path)
    candidate = _load(V95, "live")
    with pytest.raises(ProfileChangeApprovalError, match="approved_by"):
        validate_profile_change_approval(
            _load(V94), candidate, candidate.transition_approval
        )


def test_v94_to_v95_passes_offline_startup_once_operator_fields_are_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every other gate already accepts: evidence hashes, rollback, retirements."""
    _mirror(tmp_path, APPROVAL, V95)
    _rewrite(tmp_path, APPROVAL, **PLACEHOLDER)
    monkeypatch.chdir(tmp_path)
    summary = rollback.dry_run_startup(Path(V94), Path(V95))
    preflight = summary["preflight_profile_change_approval"]
    assert preflight["state"] == "approved_profile_change"
    assert preflight["retired_execution_scopes"] == []
    assert preflight["replacement_execution_scopes"] == []
    assert summary["startup_profile_change_approval"] == preflight


def test_watch_only_removal_takes_no_retirement_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mirror(tmp_path, APPROVAL, V95)
    retirement = {
        "retired_scope": {"strategy_id": HYPE_ALIGN, "symbol": "HYPE", "side": "long"},
        "replacement_scope": None,
    }
    _rewrite(tmp_path, APPROVAL, **PLACEHOLDER, retirements=[retirement])
    monkeypatch.chdir(tmp_path)
    candidate = _load(V95, "live")
    with pytest.raises(ProfileChangeApprovalError, match="retirement mappings"):
        validate_profile_change_approval(
            _load(V94), candidate, candidate.transition_approval
        )


def test_approval_rollback_cannot_name_the_rollback_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mirror(tmp_path, APPROVAL, V95)
    _rewrite(
        tmp_path,
        APPROVAL,
        **PLACEHOLDER,
        rollback={
            "config_path": f"../../{ROLLBACK}",
            "profile_fingerprint": V94_FINGERPRINT,
            "sha256": _sha256(REPOSITORY / ROLLBACK),
        },
    )
    monkeypatch.chdir(tmp_path)
    candidate = _load(V95, "live")
    with pytest.raises(ProfileChangeApprovalError, match="rollback config profile"):
        validate_profile_change_approval(
            _load(V94), candidate, candidate.transition_approval
        )


def test_rollback_profile_is_v94_with_only_the_approval_rebound() -> None:
    target = _load(REPOSITORY / V94)
    profile = _load(REPOSITORY / ROLLBACK)
    expected = copy.deepcopy(_raw(V94))
    expected["runtime"]["transition_approval"] = ROLLBACK_APPROVAL
    assert _raw(ROLLBACK) == expected
    assert profile.profile_id == target.profile_id == V94_ID
    assert profile.profile_fingerprint == ROLLBACK_FINGERPRINT
    assert profile.transition_approval == Path(ROLLBACK_APPROVAL)
    header = (REPOSITORY / ROLLBACK).read_text(encoding="utf-8").splitlines()[0]
    assert header == f"# ROLLBACK PROFILE generated by {GENERATOR}."
    document = _document(ROLLBACK_APPROVAL)
    assert document["previous_profile"] == {
        "profile_id": V95_ID,
        "profile_fingerprint": V95_FINGERPRINT,
    }
    assert document["candidate_profile"] == {
        "profile_id": V94_ID,
        "profile_fingerprint": ROLLBACK_FINGERPRINT,
    }
    assert document["rollback"] == {
        "config_path": f"../../{V95}",
        "profile_fingerprint": V95_FINGERPRINT,
        "sha256": _sha256(REPOSITORY / V95),
    }
    assert document["retirements"] == []


def test_pending_rollback_is_refused_by_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPOSITORY)
    assert (
        rollback.main(
            ["--root", str(REPOSITORY), "--current", V95, "--verify", ROLLBACK]
        )
        == 2
    )


def test_rollback_passes_offline_startup_once_operator_fields_are_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mirror(tmp_path, ROLLBACK_APPROVAL, ROLLBACK)
    _rewrite(tmp_path, ROLLBACK_APPROVAL, **PLACEHOLDER)
    monkeypatch.chdir(tmp_path)
    assert (
        rollback.main(["--root", str(tmp_path), "--current", V95, "--verify", ROLLBACK])
        == 0
    )
