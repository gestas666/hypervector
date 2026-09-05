"""Fail-closed approval contracts for cohort profile changes and retirements."""

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

_V61 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml"
)


def test_unchanged_profile_restart_needs_no_change_approval() -> None:
    """A byte-equivalent profile restart is not a strategy change."""
    config = load_multi_asset_live_config(_V61, mode="observe")

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
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-parameter-fix")

    with pytest.raises(
        ProfileChangeApprovalError,
        match="changed profile requires an exact approval document",
    ):
        validate_profile_change_approval(previous, candidate, None)


def test_research_approval_does_not_grant_live_transition_authority(
    tmp_path: Path,
) -> None:
    """The approved V62 build remains separate from live promotion."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-research-only")
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
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-invalid-header")
    approval = _write_approval(tmp_path, previous, candidate)
    document = json.loads(approval.read_text(encoding="utf-8"))
    document[field] = value
    approval.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ProfileChangeApprovalError, match=message):
        validate_profile_change_approval(previous, candidate, approval)


def test_approval_is_bound_to_exact_profile_fingerprints(tmp_path: Path) -> None:
    """An approval for an earlier candidate cannot authorize later drift."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-exact")
    approval = _write_approval(tmp_path, previous, candidate)
    drifted = replace(candidate, poll_seconds=candidate.poll_seconds + 1.0)

    with pytest.raises(
        ProfileChangeApprovalError,
        match="candidate profile fingerprint differs from approval",
    ):
        validate_profile_change_approval(previous, drifted, approval)


def test_approval_rejects_changed_evidence_bytes(tmp_path: Path) -> None:
    """Recommendation evidence must remain identical after approval."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-evidence")
    approval = _write_approval(tmp_path, previous, candidate)
    (tmp_path / "recommendation.json").write_text("drifted\n", encoding="utf-8")

    with pytest.raises(
        ProfileChangeApprovalError,
        match="recommendation evidence sha256 differs",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_approval_rejects_changed_rollback_bytes(tmp_path: Path) -> None:
    """A rollback artifact must still reproduce the prior profile exactly."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    candidate = replace(previous, profile_id="v62-rollback")
    approval = _write_approval(tmp_path, previous, candidate)
    (tmp_path / "rollback.toml").write_text("drifted\n", encoding="utf-8")

    with pytest.raises(ProfileChangeApprovalError, match="rollback config sha256"):
        validate_profile_change_approval(previous, candidate, approval)


def test_retired_scope_requires_named_added_replacement(tmp_path: Path) -> None:
    """Removing execution authority without replacement cannot be approved."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    candidate = _replace_provider(previous, retired, None)
    approval = _write_approval(tmp_path, previous, candidate)

    with pytest.raises(
        ProfileChangeApprovalError,
        match="retirement mappings differ from removed execution scopes",
    ):
        validate_profile_change_approval(previous, candidate, approval)


def test_absent_asset_scopes_allow_explicit_terminal_removal(tmp_path: Path) -> None:
    """An operator may remove an entire asset without inventing a replacement."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = next(asset for asset in previous.assets if asset.symbol == "SOL")
    provider = next(
        row for row in previous.providers if row.execution_symbols == ("SOL",)
    )
    candidate = replace(
        previous,
        profile_id="v62-sol-terminal-removal",
        assets=tuple(asset for asset in previous.assets if asset is not retired),
        providers=tuple(row for row in previous.providers if row is not provider),
    )
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            {
                "retired_scope": {
                    "strategy_id": provider.strategy_id,
                    "symbol": "SOL",
                    "side": "short",
                },
                "replacement_scope": None,
            }
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["retired_execution_scopes"] == [f"{provider.strategy_id}|SOL|short"]
    assert result["replacement_execution_scopes"] == []


def test_retained_asset_scope_allows_explicit_terminal_removal(
    tmp_path: Path,
) -> None:
    """An operator may reduce one retained asset's execution authority."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    candidate = _replace_provider(previous, retired, None)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            {
                "retired_scope": {
                    "strategy_id": retired.strategy_id,
                    "symbol": "BTC",
                    "side": "short",
                },
                "replacement_scope": None,
            }
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["retired_execution_scopes"] == [f"{retired.strategy_id}|BTC|short"]
    assert result["replacement_execution_scopes"] == []


def test_replacement_must_preserve_symbol_and_side_coverage(tmp_path: Path) -> None:
    """A short BTC retirement cannot be filled by a long BTC route."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    replacement = replace(
        retired,
        strategy_id="v62-btc-long-replacement",
        sides=frozenset({"long"}),
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
                "short",
                replacement.strategy_id,
                "BTC",
                "long",
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
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    replacement = replace(retired, strategy_id="v62-btc-short-replacement")
    candidate = _replace_provider(previous, retired, replacement)
    mapping = _retirement(
        retired.strategy_id,
        "BTC",
        "short",
        replacement.strategy_id,
        "BTC",
        "short",
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
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    existing = previous.providers[1]
    candidate = _replace_provider(previous, retired, None)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            _retirement(
                retired.strategy_id,
                "BTC",
                "short",
                existing.strategy_id,
                "BTC",
                "short",
            )
        ],
    )

    with pytest.raises(ProfileChangeApprovalError, match="must be newly added"):
        validate_profile_change_approval(previous, candidate, approval)


def test_approved_replacement_covers_every_removed_scope_once(
    tmp_path: Path,
) -> None:
    """Exact live approval accepts a complete one-to-one replacement lineage."""
    previous = load_multi_asset_live_config(_V61, mode="observe")
    retired = previous.providers[0]
    replacement = replace(retired, strategy_id="v62-btc-short-replacement")
    candidate = _replace_provider(previous, retired, replacement)
    approval = _write_approval(
        tmp_path,
        previous,
        candidate,
        retirements=[
            _retirement(
                retired.strategy_id,
                "BTC",
                "short",
                replacement.strategy_id,
                "BTC",
                "short",
            )
        ],
    )

    result = validate_profile_change_approval(previous, candidate, approval)

    assert result["state"] == "approved_profile_change"
    assert result["approval_required"] is True
    assert result["approval_status"] == "approved_for_live_transition"
    assert result["retired_execution_scopes"] == [f"{retired.strategy_id}|BTC|short"]
    assert result["replacement_execution_scopes"] == [
        f"{replacement.strategy_id}|BTC|short"
    ]
    assert result["execution_authority"] == "none"


def _replace_provider(
    config: MultiAssetLiveConfig,
    retired: StrategyProviderConfig,
    replacement: StrategyProviderConfig | None,
) -> MultiAssetLiveConfig:
    """Return a distinct profile with one provider removed or replaced."""
    providers = tuple(row for row in config.providers if row is not retired)
    if replacement is not None:
        providers = (replacement, *providers)
    return replace(config, profile_id="v62-lineage", providers=providers)


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
) -> Path:
    """Write an exact approval fixture with hash-bound evidence and rollback."""
    evidence = root / "recommendation.json"
    rollback = root / "rollback.toml"
    evidence.write_text('{"decision":"recommend"}\n', encoding="utf-8")
    rollback.write_bytes(_V61.read_bytes())
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
