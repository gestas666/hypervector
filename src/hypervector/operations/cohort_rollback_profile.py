"""Pre-author an approved cohort rollback profile and dry-run its start offline.

Report-only. execution_authority: none. No credentials, no venue client, no
network, and nothing is started, stopped or armed.

A profile file cannot be restarted as a rollback once a later profile has run.
Its ``[runtime] transition_approval`` names the approval that admitted it (V91's
names V90 -> V91), while live startup validates the change from the profile that
actually ran last (V93). ``validate_profile_change_approval`` then refuses with
"previous profile id differs from approval", and it does so only after the
mandatory pre-start bundle has been written.

This tool writes a separate rollback profile: the target's bytes, unchanged
except that ``transition_approval`` names a new approval. The approval path is
part of the profile fingerprint, so the profile is written first under its final
name, then fingerprinted with the repository's own loader, then the approval is
written for exactly that (current -> rollback) pair. The profile keeps the
target's ``profile`` id: approval and startup bind on the fingerprint, which
already differs, and the id's final ``v<generation>`` token keeps research and
cockpit generation labels on the strategy that actually runs.

Before reporting success, it calls offline what ``multi_asset_bidirectional_live.py``
calls before any venue client: the armed-mode load, ``validate_runtime_configuration``,
the accounting-epoch requirement, the separate-candidate-file rule and
``require_approved_profile_change`` against a verified-backup manifest that names
the current profile, plus the unsigned preflight's ``validate_profile_change_approval``.
Two startup gates cannot run offline: the completed drain archive of the current
run and the venue's flat, order-free boundary. The runbook's drain, archive and
unsigned-preflight steps establish both.

Existing files are never overwritten. When the dry run refuses, both new files are
removed. ``--verify`` re-runs the dry run against an existing pair without writing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib

from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT

from hypervector.live.cohort_accounting_rollover import load_required_accounting_epoch
from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    require_approved_profile_change,
    validate_profile_change_approval,
)
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError

_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
_RUNTIME_HEADER = re.compile(r"\s*\[runtime\]\s*(#.*)?")
_TABLE_HEADER = re.compile(r"\s*\[")
_APPROVAL_KEY = re.compile(r"\s*transition_approval\s*=")
_DRY_RUN_ID = "offline-rollback-dry-run"


class RollbackProfileError(ValueError):
    """A rollback pair cannot be authored or does not pass the startup gates."""


def build_parser() -> argparse.ArgumentParser:
    """Build the author-or-verify command; neither mode can start anything."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="checkout the profile paths are relative to (default: the repository root)",
    )
    parser.add_argument(
        "--current", type=Path, required=True, help="profile the live cohort runs"
    )
    parser.add_argument("--target", type=Path, help="profile to roll back to")
    parser.add_argument("--name", help="base filename for the profile and approval")
    parser.add_argument("--operator-approval", help="the operator's exact words")
    parser.add_argument("--approved-by", default="operator_in_conversation")
    parser.add_argument("--approved-at", help="ISO-8601 with timezone; default now")
    parser.add_argument(
        "--evidence",
        type=Path,
        action="append",
        default=[],
        help="additional recommendation evidence; the target is always included",
    )
    parser.add_argument("--config-dir", type=Path, default=Path("configs"))
    parser.add_argument(
        "--approval-dir", type=Path, default=Path("docs/live-approvals")
    )
    parser.add_argument(
        "--verify",
        type=Path,
        help="re-run the offline dry run for an existing rollback profile",
    )
    return parser


def render_rollback_profile(
    target_text: str,
    approval_reference: str,
    header: Sequence[str] = (),
) -> str:
    """Return target bytes with only ``[runtime] transition_approval`` rebound."""
    lines = target_text.splitlines(keepends=True)
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if _RUNTIME_HEADER.fullmatch(line.rstrip("\n"))
        ),
        None,
    )
    if start is None:
        raise RollbackProfileError("target profile has no [runtime] table")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if _TABLE_HEADER.match(lines[index])
        ),
        len(lines),
    )
    binding = f"transition_approval = {json.dumps(approval_reference)}\n"
    existing = [
        index for index in range(start + 1, end) if _APPROVAL_KEY.match(lines[index])
    ]
    if len(existing) > 1:
        raise RollbackProfileError("target binds transition_approval more than once")
    if existing:
        lines[existing[0]] = binding
    else:
        last_key = max(index for index in range(start, end) if lines[index].strip())
        if not lines[last_key].endswith("\n"):
            lines[last_key] += "\n"
        lines.insert(last_key + 1, binding)
    rendered = "".join([*(f"# {line}\n" for line in header), *lines])
    _require_only_approval_changed(target_text, rendered, approval_reference)
    return rendered


def derive_retirements(
    previous: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
) -> list[dict[str, object]]:
    """Map each scope the rollback removes to its unique same-direction successor."""
    removed = previous.executable_provider_directions.difference(
        candidate.executable_provider_directions
    )
    added = candidate.executable_provider_directions.difference(
        previous.executable_provider_directions
    )
    rows: list[dict[str, object]] = []
    for scope in sorted(removed):
        successors = [
            replacement for replacement in sorted(added) if replacement[1:] == scope[1:]
        ]
        rows.append(
            {
                "retired_scope": _scope_row(scope),
                "replacement_scope": (
                    _scope_row(successors[0]) if len(successors) == 1 else None
                ),
            }
        )
    return rows


def dry_run_startup(current_path: Path, rollback_path: Path) -> dict[str, object]:
    """Run every approval-bearing startup gate that needs no venue or archive."""
    candidate = load_multi_asset_live_config(
        rollback_path, mode="live", enabled=True, accepts_live_risk=True
    )
    validate_runtime_configuration(candidate)
    if load_required_accounting_epoch(None, candidate) is not None:
        raise RollbackProfileError("rollback profile unexpectedly bound an epoch")
    if candidate.transition_approval is None:
        raise RollbackProfileError("rollback profile binds no transition approval")
    if current_path.resolve() == rollback_path.resolve():
        raise RollbackProfileError(
            "strategy changes require a separate candidate file; "
            "the active config cannot be edited in place"
        )
    previous = load_multi_asset_live_config(current_path, mode="observe")
    if previous.profile_fingerprint == candidate.profile_fingerprint:
        raise RollbackProfileError("rollback profile is identical to the current one")
    preflight = validate_profile_change_approval(
        previous, candidate, candidate.transition_approval
    )
    with tempfile.TemporaryDirectory(prefix="rollback-dry-run-") as scratch:
        backup = _startup_backup(Path(scratch), previous, current_path)
        startup = require_approved_profile_change(candidate, backup)
    if startup is None:
        raise RollbackProfileError("startup did not treat the rollback as a change")
    return {
        "armed_load": "accepted",
        "runtime_validation": "accepted",
        "accounting_epoch": "not_required",
        "separate_candidate_file": "accepted",
        "preflight_profile_change_approval": preflight,
        "startup_profile_change_approval": startup,
        "not_run_offline": "current-run drain archive; venue flat and order-free",
    }


def create_rollback(args: argparse.Namespace) -> dict[str, object]:
    """Write the rollback pair, dry-run it, and remove both files on refusal."""
    name = _name(args.name)
    approval_text = _required_text(args.operator_approval, "--operator-approval")
    current_path = _inside_root(args.current, "--current")
    target_path = _inside_root(args.target, "--target")
    evidence = [
        target_path,
        *(_inside_root(path, "--evidence") for path in args.evidence),
    ]
    profile_path = _inside_root(args.config_dir, "--config-dir") / f"{name}.toml"
    approval_dir = _inside_root(args.approval_dir, "--approval-dir")
    approval_path = approval_dir / f"{name}.json"
    for path in (profile_path, approval_path):
        if path.exists():
            raise RollbackProfileError(f"refusing to overwrite; already exists: {path}")
    current = load_multi_asset_live_config(current_path, mode="observe")
    target = load_multi_asset_live_config(target_path, mode="observe")
    if target.profile_fingerprint == current.profile_fingerprint:
        raise RollbackProfileError("target profile is the current profile")
    approved_at = _approved_at(args.approved_at)
    rendered = render_rollback_profile(
        target_path.read_text(encoding="utf-8"),
        approval_path.as_posix(),
        _header(current, target, current_path, target_path, approval_path),
    )
    written: list[Path] = []
    try:
        _write_new(profile_path, rendered, written)
        candidate = load_multi_asset_live_config(profile_path, mode="observe")
        document = {
            "schema_version": 1,
            "document_type": "cohort_profile_change_approval",
            "approval_status": "approved_for_live_transition",
            "approved_at_utc": approved_at,
            "approved_by": _required_text(args.approved_by, "--approved-by"),
            "operator_approval": approval_text,
            "execution_authority": "none",
            "previous_profile": _identity(current),
            "candidate_profile": _identity(candidate),
            "change_scopes": [f"rollback_to_{target.profile_id}"],
            "recommendation_evidence": [
                {"path": _relative(path, approval_dir), "sha256": _sha256(path)}
                for path in dict.fromkeys(evidence)
            ],
            "rollback": {
                "config_path": _relative(current_path, approval_dir),
                "profile_fingerprint": current.profile_fingerprint,
                "sha256": _sha256(current_path),
            },
            "retirements": derive_retirements(current, candidate),
        }
        _write_new(approval_path, json.dumps(document, indent=2) + "\n", written)
        dry_run = dry_run_startup(current_path, profile_path)
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return _summary(current_path, target_path, profile_path, dry_run)


def verify_rollback(args: argparse.Namespace) -> dict[str, object]:
    """Re-run the offline startup dry run for an existing pair without writing."""
    current_path = _inside_root(args.current, "--current")
    profile_path = _inside_root(args.verify, "--verify")
    dry_run = dry_run_startup(current_path, profile_path)
    return _summary(current_path, None, profile_path, dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    """Exit 0 only when live startup's offline gates accept the rollback pair."""
    args = build_parser().parse_args(argv)
    try:
        os.chdir(REPOSITORY_ROOT if args.root is None else args.root)
        if args.verify is not None:
            if any(value is not None for value in (args.target, args.name)):
                raise RollbackProfileError("--verify takes only --current")
            summary = verify_rollback(args)
        else:
            summary = create_rollback(args)
    except (
        CohortExecutionPlanError,
        CohortTransitionDrainError,
        MultiAssetLiveConfigError,
        MultiAssetLiveRunnerError,
        OSError,
        ProfileChangeApprovalError,
        ValueError,
    ) as exc:
        print(f"rollback refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _require_only_approval_changed(
    target_text: str, rendered: str, approval_reference: str
) -> None:
    try:
        expected = tomllib.loads(target_text)
        observed = tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as exc:
        raise RollbackProfileError(
            f"rollback profile is not valid TOML: {exc}"
        ) from exc
    runtime = expected.get("runtime")
    if not isinstance(runtime, dict):
        raise RollbackProfileError("target [runtime] must be a table")
    runtime["transition_approval"] = approval_reference
    if observed != expected:
        raise RollbackProfileError("rollback profile differs from target content")


def _startup_backup(
    scratch: Path,
    previous: MultiAssetLiveConfig,
    current_path: Path,
) -> CohortPrestartBackupResult:
    """Stand in for the verified pre-start bundle that names the current run."""
    manifest = scratch / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "previous_identity": {
                    "profile_id": previous.profile_id,
                    "profile_fingerprint": previous.profile_fingerprint,
                    "run_id": _DRY_RUN_ID,
                    "config_source_path": current_path.as_posix(),
                },
                "execution_authority": "none",
            }
        ),
        encoding="utf-8",
    )
    return CohortPrestartBackupResult(
        path=scratch,
        manifest_path=manifest,
        manifest_sha256=_sha256(manifest),
        strategy_changed=True,
        implementation_file_count=0,
        implementation_sha256="0" * 64,
    )


def _summary(
    current_path: Path,
    target_path: Path | None,
    profile_path: Path,
    dry_run: dict[str, object],
) -> dict[str, object]:
    current = load_multi_asset_live_config(current_path, mode="observe")
    candidate = load_multi_asset_live_config(profile_path, mode="observe")
    approval = candidate.transition_approval
    summary: dict[str, object] = {
        "execution_authority": "none",
        "current_profile": _file_identity(current_path, current),
        "rollback_profile": _file_identity(profile_path, candidate),
        "approval": {
            "path": None if approval is None else approval.as_posix(),
            "sha256": None if approval is None else _sha256(approval),
        },
        "offline_dry_run": dry_run,
    }
    if target_path is not None:
        target = load_multi_asset_live_config(target_path, mode="observe")
        summary["target_profile"] = _file_identity(target_path, target)
    return summary


def _file_identity(path: Path, config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
    }


def _header(
    current: MultiAssetLiveConfig,
    target: MultiAssetLiveConfig,
    current_path: Path,
    target_path: Path,
    approval_path: Path,
) -> tuple[str, ...]:
    return (
        "ROLLBACK PROFILE generated by scripts/cohort_rollback_profile.py.",
        f"Content: {target_path.as_posix()} ({target.profile_fingerprint[:12]}),",
        "unchanged except [runtime] transition_approval, which admits the change",
        f"from {current.profile_id} ({current.profile_fingerprint[:12]}, "
        f"{current_path.as_posix()}).",
        f"Approval: {approval_path.as_posix()}. Start only through a drained,",
        "archived, flat and order-free boundary; this file grants no authority.",
    )


def _identity(config: MultiAssetLiveConfig) -> dict[str, str]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
    }


def _scope_row(scope: tuple[str, str, str]) -> dict[str, str]:
    return {"strategy_id": scope[0], "symbol": scope[1], "side": scope[2]}


def _name(value: str | None) -> str:
    if value is None or not _NAME.fullmatch(value):
        raise RollbackProfileError(
            "--name must be lowercase letters, digits, '_' or '-' without extension"
        )
    return value


def _inside_root(value: Path | None, label: str) -> Path:
    """Return a root-relative path, so the pair works from any checkout."""
    if value is None:
        raise RollbackProfileError(f"{label} is required")
    root = Path.cwd().resolve()
    absolute = (value if value.is_absolute() else root / value).resolve()
    try:
        return absolute.relative_to(root)
    except ValueError as exc:
        raise RollbackProfileError(f"{label} must be inside {root}: {value}") from exc


def _relative(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def _approved_at(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RollbackProfileError("--approved-at is not ISO-8601") from exc
    if parsed.utcoffset() is None:
        raise RollbackProfileError("--approved-at must include a timezone")
    return value


def _required_text(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise RollbackProfileError(f"{label} must be non-empty text")
    return value


def _write_new(path: Path, text: str, written: list[Path]) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            written.append(path)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RollbackProfileError(
            f"refusing to overwrite; already exists: {path}"
        ) from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
