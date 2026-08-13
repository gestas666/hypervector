"""Verify an immutable cohort pre-start backup without restoring live files."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys

from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    verify_cohort_prestart_backup,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only backup verification command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify every archive and print bounded non-secret identity evidence."""
    args = build_parser().parse_args(argv)
    try:
        manifest = verify_cohort_prestart_backup(args.bundle)
    except CohortPrestartBackupError as exc:
        print(f"backup verification refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_summary(args.bundle, manifest), sort_keys=True))
    return 0


def _summary(bundle: Path, manifest: Mapping[str, object]) -> dict[str, object]:
    files = manifest.get("files")
    implementation = manifest.get("implementation_identity")
    return {
        "status": "verified",
        "bundle": str(bundle),
        "created_at_utc": manifest.get("created_at_utc"),
        "strategy_changed": manifest.get("strategy_changed"),
        "previous_profile_id": _profile_id(manifest.get("previous_identity")),
        "target_profile_id": _profile_id(manifest.get("target_identity")),
        "file_count": len(files) if isinstance(files, list) else 0,
        "implementation_file_count": _mapping_value(implementation, "file_count"),
        "implementation_sha256": _mapping_value(implementation, "sha256"),
    }


def _profile_id(value: object) -> object:
    if not isinstance(value, Mapping):
        return None
    return value.get("profile_id")


def _mapping_value(value: object, key: str) -> object:
    if not isinstance(value, Mapping):
        return None
    return value.get(key)


if __name__ == "__main__":
    raise SystemExit(main())
