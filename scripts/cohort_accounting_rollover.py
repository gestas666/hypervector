#!/usr/bin/env python3
"""Prepare an immutable clean accounting epoch after a flat cohort stop."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import publish_immutable_directory, write_json
from hypervector.live.cohort_accounting_continuation import (
    build_accounting_continuation_manifest,
)
from hypervector.live.cohort_accounting_rollover import (
    build_accounting_rollover_manifest,
    load_accounting_rollover_manifest,
)
from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    verify_cohort_prestart_backup,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch
from hypervector.runtime_lock import (
    RuntimeLockError,
    bidirectional_live_runtime_lock,
    cohort_checkpoint_runtime_lock,
)

LockFn = Callable[[Path], AbstractContextManager[Path]]
VerifyBackupFn = Callable[[Path], dict[str, object]]
BuildReportFn = Callable[..., dict[str, object]]
BuildContinuationFn = Callable[..., dict[str, object]]
VerifyParentEpochFn = Callable[[Path, MultiAssetLiveConfig], CohortAccountingEpoch]
NowFn = Callable[[], datetime]


def build_parser() -> argparse.ArgumentParser:
    """Build the dry-run-by-default accounting rollover CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-config", type=Path, required=True)
    parser.add_argument("--successor-config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--prestart-bundle", type=Path, required=True)
    parser.add_argument("--parent-accounting-epoch-bundle", type=Path)
    parser.add_argument("--epoch-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="publish the verified immutable accounting epoch bundle",
    )
    return parser


def run_rollover(
    args: argparse.Namespace,
    *,
    live_lock_fn: LockFn = bidirectional_live_runtime_lock,
    checkpoint_lock_fn: LockFn = cohort_checkpoint_runtime_lock,
    verify_backup_fn: VerifyBackupFn = verify_cohort_prestart_backup,
    verify_parent_epoch_fn: VerifyParentEpochFn = load_accounting_rollover_manifest,
    build_report_fn: BuildReportFn = build_accounting_rollover_manifest,
    build_continuation_fn: BuildContinuationFn = build_accounting_continuation_manifest,
    now_fn: NowFn = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Validate stopped state and optionally publish its accounting boundary."""
    prior = load_multi_asset_live_config(args.prior_config, mode="observe")
    successor = load_multi_asset_live_config(args.successor_config, mode="observe")
    checkpoint_path = Path(args.checkpoint)
    parent_bundle = (
        Path(args.parent_accounting_epoch_bundle)
        if args.parent_accounting_epoch_bundle is not None
        else None
    )
    with live_lock_fn(prior.cohort_ledger):
        with checkpoint_lock_fn(checkpoint_path):
            if parent_bundle is not None:
                verify_parent_epoch_fn(parent_bundle, prior)
            inputs = _load_inputs(
                checkpoint_path,
                Path(args.preflight),
                Path(args.prestart_bundle),
                parent_bundle,
                verify_backup_fn,
            )
            report = _build_report(
                build_report_fn, prior, successor, inputs, str(args.epoch_id), now_fn()
            )
            report = _continue_report(build_continuation_fn, report, inputs)
            if args.yes:
                _publish(Path(args.out), report, inputs)
    _print_result(Path(args.out), report, confirmed=bool(args.yes))
    return report


def _load_inputs(
    checkpoint: Path,
    preflight: Path,
    bundle: Path,
    parent_bundle: Path | None,
    verify_backup_fn: VerifyBackupFn,
) -> dict[str, object]:
    checkpoint_json, checkpoint_bytes = _read_json(checkpoint, "checkpoint")
    preflight_json, preflight_bytes = _read_json(preflight, "preflight")
    manifest_path = bundle / "manifest.json"
    manifest_json, manifest_bytes = _read_json(manifest_path, "backup manifest")
    verified = verify_backup_fn(bundle)
    if verified != manifest_json:
        raise ValueError("verified backup manifest differs from preserved bytes")
    result: dict[str, object] = {
        "checkpoint": checkpoint_json,
        "checkpoint_bytes": checkpoint_bytes,
        "preflight": preflight_json,
        "preflight_bytes": preflight_bytes,
        "backup": verified,
        "backup_manifest_path": manifest_path,
        "backup_manifest_bytes": manifest_bytes,
    }
    if parent_bundle is not None:
        parent_json, parent_bytes = _read_json(
            parent_bundle / "manifest.json", "parent accounting epoch manifest"
        )
        result["parent_accounting_epoch"] = parent_json
        result["parent_accounting_epoch_bytes"] = parent_bytes
    return result


def _build_report(
    build_report_fn: BuildReportFn,
    prior: object,
    successor: object,
    inputs: Mapping[str, object],
    epoch_id: str,
    now: datetime,
) -> dict[str, object]:
    return build_report_fn(
        prior,
        successor,
        inputs["checkpoint"],
        inputs["preflight"],
        inputs["backup"],
        epoch_id=epoch_id,
        backup_bundle_evidence=_evidence(
            str(Path(inputs["backup_manifest_path"]).resolve()),
            _bytes(inputs["backup_manifest_bytes"]),
        ),
        checkpoint_evidence=_evidence(
            "final_checkpoint.json", _bytes(inputs["checkpoint_bytes"])
        ),
        preflight_evidence=_evidence(
            "final_preflight.json", _bytes(inputs["preflight_bytes"])
        ),
        now=now,
    )


def _continue_report(
    build_continuation_fn: BuildContinuationFn,
    report: dict[str, object],
    inputs: Mapping[str, object],
) -> dict[str, object]:
    parent = inputs.get("parent_accounting_epoch")
    if parent is None:
        return report
    if not isinstance(parent, Mapping):
        raise ValueError("parent accounting epoch manifest must be an object")
    parent_bytes = _bytes(inputs.get("parent_accounting_epoch_bytes"))
    checkpoint = inputs.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise ValueError("accounting rollover checkpoint must be an object")
    return build_continuation_fn(
        report,
        parent,
        checkpoint,
        parent_manifest_evidence=_evidence(
            "parent_accounting_epoch_manifest.json", parent_bytes
        ),
    )


def _publish(
    output: Path,
    report: Mapping[str, object],
    inputs: Mapping[str, object],
) -> None:
    def writer(staging: Path) -> None:
        (staging / "final_checkpoint.json").write_bytes(
            _bytes(inputs["checkpoint_bytes"])
        )
        (staging / "final_preflight.json").write_bytes(
            _bytes(inputs["preflight_bytes"])
        )
        parent_bytes = inputs.get("parent_accounting_epoch_bytes")
        if parent_bytes is not None:
            (staging / "parent_accounting_epoch_manifest.json").write_bytes(
                _bytes(parent_bytes)
            )
        write_json(staging / "manifest.json", report)

    publish_immutable_directory(output, writer)


def _read_json(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    raw = path.read_bytes()
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError(f"accounting rollover {label} must be a JSON object")
    return decoded, raw


def _evidence(path: str, raw: bytes) -> dict[str, object]:
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _bytes(value: object) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("accounting rollover internal evidence bytes are invalid")
    return value


def _print_result(
    output: Path, report: Mapping[str, object], *, confirmed: bool
) -> None:
    print(
        json.dumps(
            {
                "status": "published" if confirmed else "dry_run",
                "output": str(output),
                "execution_authority": report.get("execution_authority"),
                "accounting_epoch": report.get("accounting_epoch"),
            },
            sort_keys=True,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Return nonzero when exact stopped-state evidence cannot be preserved."""
    try:
        run_rollover(build_parser().parse_args(argv))
    except (
        CohortPrestartBackupError,
        FileExistsError,
        json.JSONDecodeError,
        MultiAssetLiveConfigError,
        OSError,
        RuntimeLockError,
        ValueError,
    ) as exc:
        print(f"accounting rollover refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
