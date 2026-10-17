"""Pre-authored rollback profiles pass the same approval gates live startup runs."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tomllib

import pytest

import cohort_rollback_profile as rollback
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    require_approved_profile_change,
    validate_profile_change_approval,
)
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

REPOSITORY = Path(__file__).resolve().parents[1]
# The retained live chain: V95 runs, V94 is the rollback target. V94's own
# transition approval admits V93 -> V94, so the V94 file cannot be restarted
# after V95 without a separate rollback profile.
V94 = "configs/multi_asset_growth_first_5000_review_actions_v94.toml"
V95 = "configs/multi_asset_growth_first_5000_review_fixes_v95.toml"
V94_ID = "multi_asset_growth_first_5000_review_actions_v94"
V95_ID = "multi_asset_growth_first_5000_review_fixes_v95"
V94_BOUND_APPROVAL = "docs/live-approvals/v93-to-v94-review-actions-20260924-v1.json"
V94_APPROVAL_LINE = f'transition_approval = "{V94_BOUND_APPROVAL}"'
NAME = "v95-to-v94-rollback-test-v1"
APPROVAL_TEXT = "roll back to V94 (test)"
EVIDENCE = "docs/reviews/rollback-evidence.md"
# The checked-in rollback pair the operator would start, and the documents its
# approval hash-binds.
CHECKED_IN_NAME = "v95-to-v94-rollback-20260927-v1"
CHECKED_IN_EVIDENCE = (
    "docs/reviews/2026-09-24-v93-full-review.md",
    "docs/plans/2026-09-24-v94-review-actions.md",
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository-shaped root holding real V95 (current) and V94 (target) bytes."""
    root = tmp_path / "repository"
    (root / "configs").mkdir(parents=True)
    (root / "docs/reviews").mkdir(parents=True)
    (root / "docs/live-approvals").mkdir()
    (root / V95).write_bytes((REPOSITORY / V95).read_bytes())
    (root / V94).write_bytes((REPOSITORY / V94).read_bytes())
    (root / EVIDENCE).write_text("why the rollback exists\n")
    monkeypatch.chdir(root)
    return root


def _create(root: Path, *extra: str, target: str = V94, name: str = NAME) -> int:
    return rollback.main(
        [
            "--root",
            str(root),
            "--current",
            V95,
            "--target",
            target,
            "--name",
            name,
            "--operator-approval",
            APPROVAL_TEXT,
            "--evidence",
            EVIDENCE,
            *extra,
        ]
    )


def _outputs(root: Path, name: str = NAME) -> tuple[Path, Path]:
    return (
        root / "configs" / f"{name}.toml",
        root / "docs/live-approvals" / f"{name}.json",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _startup_backup(
    tmp_path: Path, previous: MultiAssetLiveConfig, source: str
) -> CohortPrestartBackupResult:
    """The verified-backup view live startup hands to the approval gate."""
    manifest = tmp_path / "startup_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "previous_identity": {
                    "profile_id": previous.profile_id,
                    "profile_fingerprint": previous.profile_fingerprint,
                    "run_id": "bidirectional-live-test",
                    "config_source_path": source,
                }
            }
        )
    )
    return CohortPrestartBackupResult(
        path=tmp_path,
        manifest_path=manifest,
        manifest_sha256=_sha256(manifest),
        strategy_changed=True,
        implementation_file_count=1,
        implementation_sha256="0" * 64,
    )


def test_target_file_itself_is_refused_as_a_rollback() -> None:
    """Restarting V94's own file after V95 fails closed: it names V93 -> V94."""
    current = load_multi_asset_live_config(REPOSITORY / V95, mode="observe")
    target = load_multi_asset_live_config(REPOSITORY / V94, mode="observe")
    assert target.transition_approval == Path(V94_BOUND_APPROVAL)

    with pytest.raises(
        ProfileChangeApprovalError, match="previous profile id differs from approval"
    ):
        validate_profile_change_approval(current, target, target.transition_approval)


def test_rollback_profile_is_target_bytes_bound_to_the_new_approval(
    workspace: Path,
) -> None:
    assert _create(workspace) == 0
    profile, _ = _outputs(workspace)
    approval_reference = f"docs/live-approvals/{NAME}.json"

    target_text = (workspace / V94).read_text()
    rollback_text = profile.read_text()
    expected = tomllib.loads(target_text)
    expected["runtime"]["transition_approval"] = approval_reference
    assert tomllib.loads(rollback_text) == expected
    # V94 carries its own leading comments, so only the generated header (the
    # extra leading lines) is set aside; the target's comments must survive.
    rendered = rollback_text.splitlines()
    original = target_text.splitlines()
    header_length = len(rendered) - len(original)
    header, body = rendered[:header_length], rendered[header_length:]
    assert header and all(line.startswith("# ") for line in header)
    assert header[0] == (
        "# ROLLBACK PROFILE generated by scripts/cohort_rollback_profile.py."
    )
    changed = [
        (old, new) for old, new in zip(original, body, strict=True) if old != new
    ]
    assert changed == [
        (V94_APPROVAL_LINE, f'transition_approval = "{approval_reference}"')
    ]

    loaded = load_multi_asset_live_config(profile, mode="observe")
    target = load_multi_asset_live_config(V94, mode="observe")
    current = load_multi_asset_live_config(V95, mode="observe")
    assert loaded.profile_id == target.profile_id == V94_ID
    assert loaded.transition_approval == Path(approval_reference)
    assert loaded.profile_fingerprint not in {
        target.profile_fingerprint,
        current.profile_fingerprint,
    }
    assert replace(
        loaded, source_path=target.source_path, transition_approval=None
    ) == replace(target, transition_approval=None)


def test_approval_document_binds_current_to_rollback(workspace: Path) -> None:
    assert _create(workspace, "--approved-at", "2026-09-24T12:00:00+00:00") == 0
    profile, approval = _outputs(workspace)
    document = json.loads(approval.read_text())
    candidate = load_multi_asset_live_config(profile, mode="observe")
    current = load_multi_asset_live_config(V95, mode="observe")

    assert approval.read_text().endswith("]\n}\n")
    assert list(document) == [
        "schema_version",
        "document_type",
        "approval_status",
        "approved_at_utc",
        "approved_by",
        "operator_approval",
        "execution_authority",
        "previous_profile",
        "candidate_profile",
        "change_scopes",
        "recommendation_evidence",
        "rollback",
        "retirements",
    ]
    assert document["schema_version"] == 1
    assert document["document_type"] == "cohort_profile_change_approval"
    assert document["approval_status"] == "approved_for_live_transition"
    assert document["approved_at_utc"] == "2026-09-24T12:00:00+00:00"
    assert document["approved_by"] == "operator_in_conversation"
    assert document["operator_approval"] == APPROVAL_TEXT
    assert document["execution_authority"] == "none"
    assert document["previous_profile"] == {
        "profile_id": V95_ID,
        "profile_fingerprint": current.profile_fingerprint,
    }
    assert document["candidate_profile"] == {
        "profile_id": V94_ID,
        "profile_fingerprint": candidate.profile_fingerprint,
    }
    assert document["change_scopes"] == [f"rollback_to_{V94_ID}"]
    assert document["recommendation_evidence"] == [
        {"path": f"../../{V94}", "sha256": _sha256(workspace / V94)},
        {
            "path": "../reviews/rollback-evidence.md",
            "sha256": _sha256(workspace / EVIDENCE),
        },
    ]
    assert document["rollback"] == {
        "config_path": f"../../{V95}",
        "profile_fingerprint": current.profile_fingerprint,
        "sha256": _sha256(workspace / V95),
    }
    # V94's extra HYPE and SPCX providers are watch-only: no scope retires.
    assert document["retirements"] == []


def test_live_startup_gates_accept_the_rollback_offline(workspace: Path) -> None:
    """Call exactly what scripts/multi_asset_bidirectional_live.py calls, offline."""
    assert _create(workspace) == 0
    profile, approval = _outputs(workspace)
    current = load_multi_asset_live_config(V95, mode="observe")
    candidate = load_multi_asset_live_config(
        profile, mode="live", enabled=True, accepts_live_risk=True
    )

    validate_runtime_configuration(candidate)
    preflight = validate_profile_change_approval(
        current, candidate, candidate.transition_approval
    )
    startup = require_approved_profile_change(
        candidate, _startup_backup(workspace, current, V95)
    )

    assert startup == preflight
    assert startup == {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": "approved_for_live_transition",
        "approval_document": f"docs/live-approvals/{NAME}.json",
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }
    assert approval.is_file()


def test_summary_reports_identities_and_dry_run(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _create(workspace) == 0
    profile, approval = _outputs(workspace)
    summary = json.loads(capsys.readouterr().out)
    candidate = load_multi_asset_live_config(profile, mode="observe")
    current = load_multi_asset_live_config(V95, mode="observe")

    assert summary["execution_authority"] == "none"
    assert summary["rollback_profile"] == {
        "path": f"configs/{NAME}.toml",
        "sha256": _sha256(profile),
        "profile_id": V94_ID,
        "profile_fingerprint": candidate.profile_fingerprint,
    }
    assert summary["approval"] == {
        "path": f"docs/live-approvals/{NAME}.json",
        "sha256": _sha256(approval),
    }
    assert summary["current_profile"] == {
        "path": V95,
        "sha256": _sha256(workspace / V95),
        "profile_id": current.profile_id,
        "profile_fingerprint": current.profile_fingerprint,
    }
    assert summary["target_profile"]["path"] == V94
    dry_run = summary["offline_dry_run"]
    assert dry_run["runtime_validation"] == "accepted"
    assert dry_run["accounting_epoch"] == "not_required"
    assert dry_run["startup_profile_change_approval"]["state"] == (
        "approved_profile_change"
    )
    assert dry_run["preflight_profile_change_approval"]["state"] == (
        "approved_profile_change"
    )


@pytest.mark.parametrize("existing", ["profile", "approval"])
def test_existing_outputs_are_never_overwritten(
    workspace: Path, existing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    profile, approval = _outputs(workspace)
    occupied = profile if existing == "profile" else approval
    occupied.write_text("keep me\n")

    assert _create(workspace) == 2
    assert "already exists" in capsys.readouterr().err
    assert occupied.read_text() == "keep me\n"
    other = approval if existing == "profile" else profile
    assert not other.exists()


@pytest.mark.parametrize(
    "name", ["../escape", "nested/name", "profile.toml", "Upper", "", "_leading"]
)
def test_unsafe_names_are_refused(workspace: Path, name: str) -> None:
    assert _create(workspace, name=name) == 2
    assert sorted(path.name for path in (workspace / "configs").iterdir()) == sorted(
        [Path(V94).name, Path(V95).name]
    )
    assert list((workspace / "docs/live-approvals").iterdir()) == []


def test_target_equal_to_current_is_refused(workspace: Path) -> None:
    assert _create(workspace, target=V95) == 2
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_paths_outside_the_root_are_refused(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.toml"
    outside.write_bytes((REPOSITORY / V94).read_bytes())

    assert _create(workspace, target=str(outside)) == 2
    assert _create(workspace, target="../outside.toml") == 2
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_failed_dry_run_removes_the_new_files(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target the live runner would refuse leaves nothing behind to launch."""
    text = (workspace / V94).read_text()
    marker = 'execution_symbols = ["BTC"]\n'
    assert text.count(marker) == 1
    assert text.count("sizing_overrides = { BTC = ") == 1
    broken = workspace / "configs/broken_target.toml"
    broken.write_text(text.replace(marker, "execution_symbols = []\n"))

    assert _create(workspace, target="configs/broken_target.toml") == 2
    assert "provider entry sizing exceeds" in capsys.readouterr().err
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_target_without_approval_line_gets_one_in_runtime(workspace: Path) -> None:
    text = (workspace / V94).read_text()
    line = f"{V94_APPROVAL_LINE}\n"
    assert text.count(line) == 1
    bare = workspace / "configs/bare_target.toml"
    bare.write_text(text.replace(line, ""))

    assert _create(workspace, target="configs/bare_target.toml") == 0
    profile, _ = _outputs(workspace)
    parsed = tomllib.loads(profile.read_text())
    expected = tomllib.loads(bare.read_text())
    expected["runtime"]["transition_approval"] = f"docs/live-approvals/{NAME}.json"
    assert parsed == expected


def test_scopes_the_target_lacks_are_retired_without_replacement(
    workspace: Path,
) -> None:
    text = (workspace / V94).read_text()
    marker = 'execution_symbols = ["SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA"]\n'
    assert text.count(marker) == 1
    narrowed = workspace / "configs/tsla_watch_only_target.toml"
    narrowed.write_text(
        text.replace(
            marker, 'execution_symbols = ["SOL", "xyz:SNDK", "xyz:BRENTOIL"]\n'
        )
    )

    assert _create(workspace, target="configs/tsla_watch_only_target.toml") == 0
    _, approval = _outputs(workspace)
    assert json.loads(approval.read_text())["retirements"] == [
        {
            "retired_scope": {
                "strategy_id": "hourly_donchian_20_10_atr20_strong_short_v1",
                "symbol": "xyz:TSLA",
                "side": side,
            },
            "replacement_scope": None,
        }
        for side in ("long", "short")
    ]


def test_retired_scope_maps_to_the_unique_same_symbol_side_replacement() -> None:
    config = load_multi_asset_live_config(REPOSITORY / V94, mode="observe")
    btc = config.providers[0]
    assert btc.symbols == ("BTC",)
    renamed = replace(config, providers=(replace(btc, strategy_id="btc_new_v1"),))
    previous = replace(config, providers=(btc,))

    assert rollback.derive_retirements(previous, renamed) == [
        {
            "retired_scope": {
                "strategy_id": btc.strategy_id,
                "symbol": "BTC",
                "side": "long",
            },
            "replacement_scope": {
                "strategy_id": "btc_new_v1",
                "symbol": "BTC",
                "side": "long",
            },
        }
    ]


def test_verify_rechecks_an_existing_pair_and_catches_drift(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _create(workspace) == 0
    capsys.readouterr()
    arguments = [
        "--root",
        str(workspace),
        "--current",
        V95,
        "--verify",
        f"configs/{NAME}.toml",
    ]

    assert rollback.main(arguments) == 0
    assert (
        json.loads(capsys.readouterr().out)["offline_dry_run"][
            "startup_profile_change_approval"
        ]["state"]
        == "approved_profile_change"
    )

    (workspace / EVIDENCE).write_text("edited after approval\n")
    assert rollback.main(arguments) == 2
    assert "recommendation evidence sha256 differs" in capsys.readouterr().err


def test_verify_refuses_the_unbound_target_file(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bound = V94_BOUND_APPROVAL
    (workspace / bound).write_bytes((REPOSITORY / bound).read_bytes())
    arguments = ["--root", str(workspace), "--current", V95, "--verify", V94]

    assert rollback.main(arguments) == 2
    assert "previous profile id differs from approval" in capsys.readouterr().err


@pytest.fixture
def checked_in_workspace(workspace: Path) -> Path:
    """The workspace plus the documents the checked-in rollback approval binds."""
    (workspace / "docs/plans").mkdir()
    for path in CHECKED_IN_EVIDENCE:
        (workspace / path).write_bytes((REPOSITORY / path).read_bytes())
    return workspace


def test_the_checked_in_rollback_pair_is_what_the_tool_writes(
    checked_in_workspace: Path,
) -> None:
    """Re-authoring V95 -> V94 reproduces the checked-in pair byte for byte."""
    checked_in = json.loads(
        (REPOSITORY / f"docs/live-approvals/{CHECKED_IN_NAME}.json").read_text()
    )
    arguments = [
        "--root",
        str(checked_in_workspace),
        "--current",
        V95,
        "--target",
        V94,
        "--name",
        CHECKED_IN_NAME,
        "--operator-approval",
        checked_in["operator_approval"],
        "--approved-at",
        checked_in["approved_at_utc"],
    ]
    for path in CHECKED_IN_EVIDENCE:
        arguments += ["--evidence", path]

    assert rollback.main(arguments) == 0

    profile, approval = _outputs(checked_in_workspace, CHECKED_IN_NAME)
    assert profile.read_bytes() == (
        REPOSITORY / f"configs/{CHECKED_IN_NAME}.toml"
    ).read_bytes()
    assert approval.read_bytes() == (
        REPOSITORY / f"docs/live-approvals/{CHECKED_IN_NAME}.json"
    ).read_bytes()


def test_the_checked_in_rollback_pair_passes_the_offline_startup_gates(
    checked_in_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The restartable V94 rollback still verifies against the V95 that runs."""
    for path in (
        f"configs/{CHECKED_IN_NAME}.toml",
        f"docs/live-approvals/{CHECKED_IN_NAME}.json",
    ):
        (checked_in_workspace / path).write_bytes((REPOSITORY / path).read_bytes())
    arguments = [
        "--root",
        str(checked_in_workspace),
        "--current",
        V95,
        "--verify",
        f"configs/{CHECKED_IN_NAME}.toml",
    ]

    assert rollback.main(arguments) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["current_profile"]["profile_id"] == V95_ID
    assert summary["rollback_profile"]["profile_id"] == V94_ID
    assert summary["approval"]["path"] == (
        f"docs/live-approvals/{CHECKED_IN_NAME}.json"
    )
    assert summary["offline_dry_run"]["startup_profile_change_approval"] == {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": "approved_for_live_transition",
        "approval_document": f"docs/live-approvals/{CHECKED_IN_NAME}.json",
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }

    (checked_in_workspace / CHECKED_IN_EVIDENCE[1]).write_text("edited\n")
    assert rollback.main(arguments) == 2
    assert "recommendation evidence sha256 differs" in capsys.readouterr().err
