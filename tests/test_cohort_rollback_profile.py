"""Pre-authored rollback profiles pass the same approval gates live startup runs."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tomllib

import pytest

import hypervector.operations.cohort_rollback_profile as rollback
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
# The profile chain: B runs, A is the rollback target. A's own transition
# approval admits an earlier change into A, so the A file cannot be restarted
# after B without a separate rollback profile.
CHAIN = "tests/fixtures/cohort_chain"
APPROVAL_DIR = f"{CHAIN}/approvals"
PROFILE_A = f"{CHAIN}/profile_a.toml"
PROFILE_B = f"{CHAIN}/profile_b.toml"
PROFILE_A_ID = "fixture_cohort_a"
PROFILE_B_ID = "fixture_cohort_b"
PROFILE_A_BOUND_APPROVAL = f"{APPROVAL_DIR}/origin-to-a.json"
PROFILE_A_APPROVAL_LINE = f'transition_approval = "{PROFILE_A_BOUND_APPROVAL}"'
NAME = "b-to-a-rollback-test"
APPROVAL_TEXT = "roll back to profile A (test)"
EVIDENCE = f"{CHAIN}/evidence/rollback-evidence.md"
# The checked-in rollback pair the operator would start, and the evidence its
# approval hash-binds.
CHECKED_IN_NAME = "rollback_b_to_a"
CHECKED_IN_EVIDENCE = (f"{CHAIN}/evidence/rollback.md",)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository-shaped root holding profile B (current) and A (target) bytes."""
    root = tmp_path / "repository"
    (root / APPROVAL_DIR).mkdir(parents=True)
    (root / EVIDENCE).parent.mkdir()
    for path in (PROFILE_B, PROFILE_A):
        (root / path).write_bytes((REPOSITORY / path).read_bytes())
    (root / EVIDENCE).write_text("why the rollback exists\n")
    monkeypatch.chdir(root)
    return root


def _create(root: Path, *extra: str, target: str = PROFILE_A, name: str = NAME) -> int:
    return rollback.main(
        [
            "--root",
            str(root),
            "--current",
            PROFILE_B,
            "--target",
            target,
            "--name",
            name,
            "--config-dir",
            CHAIN,
            "--approval-dir",
            APPROVAL_DIR,
            "--operator-approval",
            APPROVAL_TEXT,
            "--evidence",
            EVIDENCE,
            *extra,
        ]
    )


def _outputs(root: Path, name: str = NAME) -> tuple[Path, Path]:
    return (
        root / CHAIN / f"{name}.toml",
        root / APPROVAL_DIR / f"{name}.json",
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


def _write_bound_approval(root: Path) -> None:
    """The approval profile A binds: it admitted an earlier profile -> A."""
    target = load_multi_asset_live_config(root / PROFILE_A, mode="observe")
    document = {
        "schema_version": 1,
        "document_type": "cohort_profile_change_approval",
        "approval_status": "approved_for_live_transition",
        "approved_at_utc": "2026-10-19T00:00:00+00:00",
        "approved_by": "test_fixture",
        "operator_approval": "fixture approval: origin to profile A",
        "execution_authority": "none",
        "previous_profile": {
            "profile_id": "fixture_cohort_origin",
            "profile_fingerprint": "0" * 64,
        },
        "candidate_profile": {
            "profile_id": PROFILE_A_ID,
            "profile_fingerprint": target.profile_fingerprint,
        },
        "change_scopes": ["origin_to_profile_a"],
        "recommendation_evidence": [
            {"path": "../profile_a.toml", "sha256": _sha256(root / PROFILE_A)}
        ],
        "rollback": {
            "config_path": "../origin.toml",
            "profile_fingerprint": "0" * 64,
            "sha256": "0" * 64,
        },
        "retirements": [],
    }
    (root / PROFILE_A_BOUND_APPROVAL).write_text(json.dumps(document, indent=2))


def test_target_file_itself_is_refused_as_a_rollback(workspace: Path) -> None:
    """Restarting A's own file after B fails closed: it names an earlier -> A."""
    current = load_multi_asset_live_config(PROFILE_B, mode="observe")
    target = load_multi_asset_live_config(PROFILE_A, mode="observe")
    assert target.transition_approval == Path(PROFILE_A_BOUND_APPROVAL)

    with pytest.raises(ProfileChangeApprovalError, match="does not exist"):
        validate_profile_change_approval(current, target, target.transition_approval)

    _write_bound_approval(workspace)
    with pytest.raises(
        ProfileChangeApprovalError, match="previous profile id differs from approval"
    ):
        validate_profile_change_approval(current, target, target.transition_approval)


def test_rollback_profile_is_target_bytes_bound_to_the_new_approval(
    workspace: Path,
) -> None:
    assert _create(workspace) == 0
    profile, _ = _outputs(workspace)
    approval_reference = f"{APPROVAL_DIR}/{NAME}.json"

    target_text = (workspace / PROFILE_A).read_text()
    rollback_text = profile.read_text()
    expected = tomllib.loads(target_text)
    expected["runtime"]["transition_approval"] = approval_reference
    assert tomllib.loads(rollback_text) == expected
    # Only the generated header (the extra leading lines) is set aside; every
    # target line but the approval binding must survive unchanged.
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
        (PROFILE_A_APPROVAL_LINE, f'transition_approval = "{approval_reference}"')
    ]

    loaded = load_multi_asset_live_config(profile, mode="observe")
    target = load_multi_asset_live_config(PROFILE_A, mode="observe")
    current = load_multi_asset_live_config(PROFILE_B, mode="observe")
    assert loaded.profile_id == target.profile_id == PROFILE_A_ID
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
    current = load_multi_asset_live_config(PROFILE_B, mode="observe")

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
        "profile_id": PROFILE_B_ID,
        "profile_fingerprint": current.profile_fingerprint,
    }
    assert document["candidate_profile"] == {
        "profile_id": PROFILE_A_ID,
        "profile_fingerprint": candidate.profile_fingerprint,
    }
    assert document["change_scopes"] == [f"rollback_to_{PROFILE_A_ID}"]
    assert document["recommendation_evidence"] == [
        {"path": "../profile_a.toml", "sha256": _sha256(workspace / PROFILE_A)},
        {
            "path": "../evidence/rollback-evidence.md",
            "sha256": _sha256(workspace / EVIDENCE),
        },
    ]
    assert document["rollback"] == {
        "config_path": "../profile_b.toml",
        "profile_fingerprint": current.profile_fingerprint,
        "sha256": _sha256(workspace / PROFILE_B),
    }
    # Profile A's extra HYPE and xyz:BBB providers are watch-only: no scope
    # retires.
    assert document["retirements"] == []


def test_live_startup_gates_accept_the_rollback_offline(workspace: Path) -> None:
    """Call exactly what scripts/multi_asset_bidirectional_live.py calls, offline."""
    assert _create(workspace) == 0
    profile, approval = _outputs(workspace)
    current = load_multi_asset_live_config(PROFILE_B, mode="observe")
    candidate = load_multi_asset_live_config(
        profile, mode="live", enabled=True, accepts_live_risk=True
    )

    validate_runtime_configuration(candidate)
    preflight = validate_profile_change_approval(
        current, candidate, candidate.transition_approval
    )
    startup = require_approved_profile_change(
        candidate, _startup_backup(workspace, current, PROFILE_B)
    )

    assert startup == preflight
    assert startup == {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": "approved_for_live_transition",
        "approval_document": f"{APPROVAL_DIR}/{NAME}.json",
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
    current = load_multi_asset_live_config(PROFILE_B, mode="observe")

    assert summary["execution_authority"] == "none"
    assert summary["rollback_profile"] == {
        "path": f"{CHAIN}/{NAME}.toml",
        "sha256": _sha256(profile),
        "profile_id": PROFILE_A_ID,
        "profile_fingerprint": candidate.profile_fingerprint,
    }
    assert summary["approval"] == {
        "path": f"{APPROVAL_DIR}/{NAME}.json",
        "sha256": _sha256(approval),
    }
    assert summary["current_profile"] == {
        "path": PROFILE_B,
        "sha256": _sha256(workspace / PROFILE_B),
        "profile_id": current.profile_id,
        "profile_fingerprint": current.profile_fingerprint,
    }
    assert summary["target_profile"]["path"] == PROFILE_A
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
    assert sorted(path.name for path in (workspace / CHAIN).glob("*.toml")) == sorted(
        [Path(PROFILE_A).name, Path(PROFILE_B).name]
    )
    assert list((workspace / APPROVAL_DIR).iterdir()) == []


def test_target_equal_to_current_is_refused(workspace: Path) -> None:
    assert _create(workspace, target=PROFILE_B) == 2
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_paths_outside_the_root_are_refused(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.toml"
    outside.write_bytes((REPOSITORY / PROFILE_A).read_bytes())

    assert _create(workspace, target=str(outside)) == 2
    assert _create(workspace, target="../outside.toml") == 2
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_failed_dry_run_removes_the_new_files(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target the live runner would refuse leaves nothing behind to launch."""
    text = (workspace / PROFILE_A).read_text()
    marker = 'execution_symbols = ["BTC"]\n'
    assert text.count(marker) == 1
    assert text.count("sizing_overrides = { BTC = ") == 1
    broken = workspace / CHAIN / "broken_target.toml"
    broken.write_text(text.replace(marker, "execution_symbols = []\n"))

    assert _create(workspace, target=f"{CHAIN}/broken_target.toml") == 2
    assert "provider entry sizing exceeds" in capsys.readouterr().err
    profile, approval = _outputs(workspace)
    assert not profile.exists() and not approval.exists()


def test_target_without_approval_line_gets_one_in_runtime(workspace: Path) -> None:
    text = (workspace / PROFILE_A).read_text()
    line = f"{PROFILE_A_APPROVAL_LINE}\n"
    assert text.count(line) == 1
    bare = workspace / CHAIN / "bare_target.toml"
    bare.write_text(text.replace(line, ""))

    assert _create(workspace, target=f"{CHAIN}/bare_target.toml") == 0
    profile, _ = _outputs(workspace)
    parsed = tomllib.loads(profile.read_text())
    expected = tomllib.loads(bare.read_text())
    expected["runtime"]["transition_approval"] = f"{APPROVAL_DIR}/{NAME}.json"
    assert parsed == expected


def test_scopes_the_target_lacks_are_retired_without_replacement(
    workspace: Path,
) -> None:
    text = (workspace / PROFILE_A).read_text()
    marker = 'execution_symbols = ["SOL", "xyz:CCC", "xyz:EEE", "xyz:FFF"]\n'
    assert text.count(marker) == 1
    narrowed = workspace / CHAIN / "fff_watch_only_target.toml"
    narrowed.write_text(
        text.replace(
            marker, 'execution_symbols = ["SOL", "xyz:CCC", "xyz:EEE"]\n'
        )
    )

    assert _create(workspace, target=f"{CHAIN}/fff_watch_only_target.toml") == 0
    _, approval = _outputs(workspace)
    assert json.loads(approval.read_text())["retirements"] == [
        {
            "retired_scope": {
                "strategy_id": "test_channel_short_15m",
                "symbol": "xyz:FFF",
                "side": side,
            },
            "replacement_scope": None,
        }
        for side in ("long", "short")
    ]


def test_retired_scope_maps_to_the_unique_same_symbol_side_replacement() -> None:
    config = load_multi_asset_live_config(REPOSITORY / PROFILE_A, mode="observe")
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
        PROFILE_B,
        "--verify",
        f"{CHAIN}/{NAME}.toml",
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
    _write_bound_approval(workspace)
    arguments = [
        "--root",
        str(workspace),
        "--current",
        PROFILE_B,
        "--verify",
        PROFILE_A,
    ]

    assert rollback.main(arguments) == 2
    assert "previous profile id differs from approval" in capsys.readouterr().err


@pytest.fixture
def checked_in_workspace(workspace: Path) -> Path:
    """The workspace plus the documents the checked-in rollback approval binds."""
    for path in CHECKED_IN_EVIDENCE:
        (workspace / path).write_bytes((REPOSITORY / path).read_bytes())
    return workspace


def test_the_checked_in_rollback_pair_is_what_the_tool_writes(
    checked_in_workspace: Path,
) -> None:
    """Re-authoring B -> A reproduces the checked-in pair byte for byte."""
    checked_in = json.loads(
        (REPOSITORY / APPROVAL_DIR / f"{CHECKED_IN_NAME}.json").read_text()
    )
    arguments = [
        "--root",
        str(checked_in_workspace),
        "--current",
        PROFILE_B,
        "--target",
        PROFILE_A,
        "--name",
        CHECKED_IN_NAME,
        "--config-dir",
        CHAIN,
        "--approval-dir",
        APPROVAL_DIR,
        "--operator-approval",
        checked_in["operator_approval"],
        "--approved-by",
        checked_in["approved_by"],
        "--approved-at",
        checked_in["approved_at_utc"],
    ]
    for path in CHECKED_IN_EVIDENCE:
        arguments += ["--evidence", path]

    assert rollback.main(arguments) == 0

    profile, approval = _outputs(checked_in_workspace, CHECKED_IN_NAME)
    assert profile.read_bytes() == (
        REPOSITORY / CHAIN / f"{CHECKED_IN_NAME}.toml"
    ).read_bytes()
    assert approval.read_bytes() == (
        REPOSITORY / APPROVAL_DIR / f"{CHECKED_IN_NAME}.json"
    ).read_bytes()


def test_the_checked_in_rollback_pair_passes_the_offline_startup_gates(
    checked_in_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The restartable A rollback still verifies against the B that runs."""
    for path in (
        f"{CHAIN}/{CHECKED_IN_NAME}.toml",
        f"{APPROVAL_DIR}/{CHECKED_IN_NAME}.json",
    ):
        (checked_in_workspace / path).write_bytes((REPOSITORY / path).read_bytes())
    arguments = [
        "--root",
        str(checked_in_workspace),
        "--current",
        PROFILE_B,
        "--verify",
        f"{CHAIN}/{CHECKED_IN_NAME}.toml",
    ]

    assert rollback.main(arguments) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["current_profile"]["profile_id"] == PROFILE_B_ID
    assert summary["rollback_profile"]["profile_id"] == PROFILE_A_ID
    assert summary["approval"]["path"] == f"{APPROVAL_DIR}/{CHECKED_IN_NAME}.json"
    assert summary["offline_dry_run"]["startup_profile_change_approval"] == {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": "approved_for_live_transition",
        "approval_document": f"{APPROVAL_DIR}/{CHECKED_IN_NAME}.json",
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }

    (checked_in_workspace / CHECKED_IN_EVIDENCE[0]).write_text("edited\n")
    assert rollback.main(arguments) == 2
    assert "recommendation evidence sha256 differs" in capsys.readouterr().err
