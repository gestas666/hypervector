"""Fail-closed approval contracts for cohort profile changes and retirements.

The synthetic lineage cases are built from fixture profile B; the A -> B
approval and the B -> A rollback approval are validated as-is.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_CHAIN = Path("tests/fixtures/cohort_chain")
_PROFILE_A = _CHAIN / "profile_a.toml"
_PROFILE_B = _CHAIN / "profile_b.toml"
_ROLLBACK_B_TO_A = _CHAIN / "rollback_b_to_a.toml"
_BTC_SWEEP = "test_long_target_1m"
_DONCHIAN = "test_channel_short_15m"
_DONCHIAN_SYMBOLS = '["SOL", "xyz:CCC", "xyz:EEE", "xyz:FFF"]'


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(path, mode="observe")


def _provider(config: MultiAssetLiveConfig, strategy_id: str) -> StrategyProviderConfig:
    return next(row for row in config.providers if row.strategy_id == strategy_id)


def test_a_to_b_approval_admits_the_live_transition() -> None:
    """Profile B's approval binds A -> B exactly and retires no scope."""
    previous = _load(_PROFILE_A)
    candidate = _load(_PROFILE_B)

    result = validate_profile_change_approval(
        previous, candidate, candidate.transition_approval
    )

    assert result == {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": "approved_for_live_transition",
        "approval_document": str(candidate.transition_approval),
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }


def test_b_to_a_rollback_approval_admits_the_rollback() -> None:
    """The authored rollback approval binds B -> rollback-A exactly."""
    previous = _load(_PROFILE_B)
    candidate = _load(_ROLLBACK_B_TO_A)

    result = validate_profile_change_approval(
        previous, candidate, candidate.transition_approval
    )

    assert result["state"] == "approved_profile_change"
    assert result["approval_document"] == str(candidate.transition_approval)
    assert result["retired_execution_scopes"] == []
    assert result["execution_authority"] == "none"


def test_approvals_do_not_transfer_between_profile_a_twins() -> None:
    """A and its rollback twin differ only by approval path, never interchangeably."""
    profile_a = _load(_PROFILE_A)
    rollback = _load(_ROLLBACK_B_TO_A)
    profile_b = _load(_PROFILE_B)

    with pytest.raises(
        ProfileChangeApprovalError,
        match="previous profile fingerprint differs from approval",
    ):
        validate_profile_change_approval(
            rollback, profile_b, profile_b.transition_approval
        )
    with pytest.raises(
        ProfileChangeApprovalError,
        match="candidate profile fingerprint differs from approval",
    ):
        validate_profile_change_approval(
            profile_b, profile_a, rollback.transition_approval
        )
    with pytest.raises(
        ProfileChangeApprovalError,
        match="previous profile id differs from approval",
    ):
        validate_profile_change_approval(
            profile_a, profile_b, rollback.transition_approval
        )
    with pytest.raises(
        ProfileChangeApprovalError,
        match="approval document does not exist",
    ):
        validate_profile_change_approval(
            profile_b, profile_a, profile_a.transition_approval
        )


def test_unchanged_profile_restart_needs_no_change_approval() -> None:
    """A byte-equivalent profile restart is not a strategy change."""
    config = _load(_PROFILE_B)

    result = validate_profile_change_approval(config, config, None)

    assert result == {
        "state": "unchanged_profile",
        "approval_required": False,
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }


def test_changed_profile_without_approval_fails_closed() -> None:
    """A changed execution contract cannot inherit approval implicitly."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-parameter-fix")

    with pytest.raises(
        ProfileChangeApprovalError,
        match="changed profile requires an exact approval document",
    ):
        validate_profile_change_approval(previous, candidate, None)


def test_research_approval_does_not_grant_live_transition_authority(
    tmp_path: Path,
) -> None:
    """An approved research build remains separate from live promotion."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-research-only")
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        status="approved_for_research",
    )

    with pytest.raises(
        ProfileChangeApprovalError,
        match="approval status is not approved_for_live_transition",
    ):
        validate_profile_change_approval(previous, candidate, approval)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version must be 1"),
        ("document_type", "other", "document_type is invalid"),
        ("execution_authority", "live", "must not grant execution authority"),
        ("approved_by", "", "approved_by must be non-empty text"),
        ("approved_at_utc", "invalid", "approved_at_utc is invalid"),
        ("approved_at_utc", "2026-08-29T12:00:00", "must include a timezone"),
        ("change_scopes", [], "must be a non-empty text array"),
    ],
)
def test_malformed_approval_headers_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    """Malformed governance metadata cannot be interpreted as approval."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-invalid-header")
    approval = _write_approval(tmp_path, previous, candidate)
    document = json.loads(approval.read_text(encoding="utf-8"))
    document[field] = value
    approval.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ProfileChangeApprovalError, match=message):
        validate_profile_change_approval(previous, candidate, approval)


def test_approval_is_bound_to_exact_profile_fingerprints(tmp_path: Path) -> None:
    """An approval for an earlier candidate cannot authorize later drift."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-exact")
    approval = _write_approval(tmp_path, previous, candidate)
    drifted = replace(candidate, poll_seconds=candidate.poll_seconds + 1.0)

    with pytest.raises(
        ProfileChangeApprovalError,
        match="candidate profile fingerprint differs from approval",
    ):
        validate_profile_change_approval(previous, drifted, approval)


def test_approval_rejects_changed_evidence_bytes(tmp_path: Path) -> None:
    """Recommendation evidence must remain identical after approval."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-evidence")
    approval = _write_approval(tmp_path, previous, candidate)
    (tmp_path / "recommendation.json").write_text("drifted\n", encoding="utf-8")

    with pytest.raises(
        ProfileChangeApprovalError,
        match="recommendation evidence sha256 differs",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_approval_rejects_changed_rollback_bytes(tmp_path: Path) -> None:
    """A rollback artifact must still reproduce the prior profile exactly."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-rollback")
    approval = _write_approval(tmp_path, previous, candidate)
    (tmp_path / "rollback.toml").write_text("drifted\n", encoding="utf-8")

    with pytest.raises(ProfileChangeApprovalError, match="rollback config sha256"):
        validate_profile_change_approval(previous, candidate, approval)


def test_rollback_must_reproduce_previous_profile(tmp_path: Path) -> None:
    """A hash-matched rollback file for another profile is not a rollback."""
    previous = _load(_PROFILE_B)
    candidate = replace(previous, profile_id="candidate-wrong-rollback")
    approval = _write_approval(
        tmp_path, previous, candidate, rollback_source=_PROFILE_A
    )

    with pytest.raises(
        ProfileChangeApprovalError,
        match="rollback config profile identity differs",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_retired_scope_requires_named_added_replacement(tmp_path: Path) -> None:
    """Removing execution authority without replacement cannot be approved."""
    previous = _load(_PROFILE_B)
    retired = _provider(previous, _BTC_SWEEP)
    candidate = _replace_provider(previous, retired, None)
    approval = _write_approval(tmp_path, previous, candidate)

    with pytest.raises(
        ProfileChangeApprovalError,
        match="retirement mappings differ from removed execution scopes",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_absent_asset_scopes_allow_explicit_terminal_removal(tmp_path: Path) -> None:
    """An operator may remove an entire asset without inventing a replacement."""
    previous = _load(_PROFILE_B)
    shared = _provider(previous, _DONCHIAN)
    narrowed = replace(
        shared,
        symbols=tuple(row for row in shared.symbols if row != "xyz:FFF"),
        execution_symbols=tuple(
            row for row in shared.execution_symbols if row != "xyz:FFF"
        ),
    )
    candidate = replace(
        _replace_provider(previous, shared, narrowed),
        profile_id="candidate-fff-terminal-removal",
        assets=tuple(row for row in previous.assets if row.symbol != "xyz:FFF"),
    )
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            {
                "retired_scope": {
                    "strategy_id": _DONCHIAN,
                    "symbol": "xyz:FFF",
                    "side": side,
                },
                "replacement_scope": None,
            }
            for side in ("long", "short")
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["retired_execution_scopes"] == [
        f"{_DONCHIAN}|xyz:FFF|long",
        f"{_DONCHIAN}|xyz:FFF|short",
    ]
    assert result["replacement_execution_scopes"] == []


def test_retained_asset_scope_allows_explicit_terminal_removal(
    tmp_path: Path,
) -> None:
    """An operator may reduce one retained asset's execution authority."""
    previous = _load(_PROFILE_B)
    retired = _provider(previous, _BTC_SWEEP)
    candidate = _replace_provider(previous, retired, None)
    assert "BTC" in candidate.symbols
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            {
                "retired_scope": {
                    "strategy_id": retired.strategy_id,
                    "symbol": "BTC",
                    "side": "long",
                },
                "replacement_scope": None,
            }
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["retired_execution_scopes"] == [f"{retired.strategy_id}|BTC|long"]
    assert result["replacement_execution_scopes"] == []


def test_replacement_must_preserve_symbol_and_side_coverage(tmp_path: Path) -> None:
    """A long BTC retirement cannot be filled by a short BTC route."""
    previous = _load(_PROFILE_B)
    retired = _provider(previous, _BTC_SWEEP)
    replacement = replace(
        retired,
        strategy_id="candidate-btc-short-replacement",
        sides=frozenset({"short"}),
    )
    candidate = _replace_provider(previous, retired, replacement)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            _retirement(
                retired.strategy_id,
                "BTC",
                "long",
                replacement.strategy_id,
                "BTC",
                "short",
            )
        ],
    )

    with pytest.raises(
        ProfileChangeApprovalError,
        match="replacement must preserve retired symbol and side",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_retired_scope_cannot_be_mapped_twice(tmp_path: Path) -> None:
    """Duplicate mappings cannot disguise incomplete one-to-one lineage."""
    previous = _load(_PROFILE_B)
    retired = _provider(previous, _BTC_SWEEP)
    replacement = replace(retired, strategy_id="candidate-btc-long-replacement")
    candidate = _replace_provider(previous, retired, replacement)
    mapping = _retirement(
        retired.strategy_id,
        "BTC",
        "long",
        replacement.strategy_id,
        "BTC",
        "long",
    )
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[mapping, mapping],
    )

    with pytest.raises(ProfileChangeApprovalError, match="must be unique"):
        validate_profile_change_approval(previous, candidate, approval)


def test_replacement_scope_must_be_newly_added(tmp_path: Path) -> None:
    """An existing provider cannot be relabeled as a retirement replacement."""
    source = _write_shared_btc_long_profile(tmp_path)
    previous = _load(source)
    retired = _provider(previous, _BTC_SWEEP)
    existing = _provider(previous, _DONCHIAN)
    assert (existing.strategy_id, "BTC", "long") in (
        previous.executable_provider_directions
    )
    candidate = _replace_provider(previous, retired, None)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        rollback_source=source,
        retirements=[
            _retirement(
                retired.strategy_id,
                "BTC",
                "long",
                existing.strategy_id,
                "BTC",
                "long",
            )
        ],
    )

    with pytest.raises(ProfileChangeApprovalError, match="must be newly added"):
        validate_profile_change_approval(previous, candidate, approval)


def test_approved_replacement_covers_every_removed_scope_once(
    tmp_path: Path,
) -> None:
    """Exact live approval accepts a complete one-to-one replacement lineage."""
    previous = _load(_PROFILE_B)
    retired = _provider(previous, _BTC_SWEEP)
    replacement = replace(retired, strategy_id="candidate-btc-long-replacement")
    candidate = _replace_provider(previous, retired, replacement)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            _retirement(
                retired.strategy_id,
                "BTC",
                "long",
                replacement.strategy_id,
                "BTC",
                "long",
            )
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["state"] == "approved_profile_change"
    assert result["approval_required"] is True
    assert result["approval_status"] == "approved_for_live_transition"
    assert result["retired_execution_scopes"] == [f"{retired.strategy_id}|BTC|long"]
    assert result["replacement_execution_scopes"] == [
        f"{replacement.strategy_id}|BTC|long"
    ]
    assert result["execution_authority"] == "none"


def _write_shared_btc_long_profile(root: Path) -> Path:
    """Write a profile B variant whose Donchian route also executes BTC both ways."""
    text = _PROFILE_B.read_text(encoding="utf-8")
    assert text.count(_DONCHIAN_SYMBOLS) == 2
    path = root / "previous.toml"
    path.write_text(
        text.replace(_DONCHIAN_SYMBOLS, _DONCHIAN_SYMBOLS.replace("[", '["BTC", ')),
        encoding="utf-8",
    )
    return path


def _replace_provider(
    config: MultiAssetLiveConfig,
    retired: StrategyProviderConfig,
    replacement: StrategyProviderConfig | None,
) -> MultiAssetLiveConfig:
    """Return a distinct profile with one provider removed or replaced."""
    providers = tuple(row for row in config.providers if row is not retired)
    if replacement is not None:
        providers = (replacement, *providers)
    return replace(config, profile_id="candidate-lineage", providers=providers)


def _retirement(
    retired_strategy: str,
    retired_symbol: str,
    retired_side: str,
    replacement_strategy: str,
    replacement_symbol: str,
    replacement_side: str,
) -> dict[str, object]:
    """Build one route-level retirement lineage fixture."""
    return {
        "retired_scope": {
            "strategy_id": retired_strategy,
            "symbol": retired_symbol,
            "side": retired_side,
        },
        "replacement_scope": {
            "strategy_id": replacement_strategy,
            "symbol": replacement_symbol,
            "side": replacement_side,
        },
    }


def _write_approval(
    root: Path,
    previous: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
    *,
    status: str = "approved_for_live_transition",
    retirements: list[dict[str, object]] | None = None,
    rollback_source: Path = _PROFILE_B,
) -> Path:
    """Write an exact approval fixture with hash-bound evidence and rollback."""
    evidence = root / "recommendation.json"
    rollback = root / "rollback.toml"
    evidence.write_text('{"decision":"recommend"}\n', encoding="utf-8")
    rollback.write_bytes(rollback_source.read_bytes())
    document = {
        "schema_version": 1,
        "document_type": "cohort_profile_change_approval",
        "approval_status": status,
        "approved_at_utc": "2026-08-29T12:00:00+00:00",
        "approved_by": "operator",
        "operator_approval": "Approve the exact fingerprint-bound transition.",
        "execution_authority": "none",
        "previous_profile": {
            "profile_id": previous.profile_id,
            "profile_fingerprint": previous.profile_fingerprint,
        },
        "candidate_profile": {
            "profile_id": candidate.profile_id,
            "profile_fingerprint": candidate.profile_fingerprint,
        },
        "change_scopes": ["strategy_replacement"],
        "recommendation_evidence": [
            {"path": evidence.name, "sha256": _sha256(evidence)}
        ],
        "rollback": {
            "config_path": rollback.name,
            "profile_fingerprint": previous.profile_fingerprint,
            "sha256": _sha256(rollback),
        },
        "retirements": retirements or [],
    }
    path = root / "approval.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    """Return one test fixture's content identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
