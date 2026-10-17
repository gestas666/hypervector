"""Create a verified source baseline before editing a cohort strategy."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys

from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT

from hypervector.live.cohort_implementation_sources import (
    discover_cohort_implementation_sources,
)
from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    CohortPrestartBackupResult,
    create_cohort_prestart_backup,
    verify_cohort_prestart_backup,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

# The checkout that holds scripts/ and src/, as the live entrypoint sees it.
_REPOSITORY_ROOT = REPOSITORY_ROOT


def build_parser() -> argparse.ArgumentParser:
    """Build the credential-free pre-change snapshot command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="cohort profile TOML to snapshot"
    )
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=Path("../backtest-lab/backtest_lab"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Capture and independently verify the current implementation bytes."""
    args = build_parser().parse_args(argv)
    try:
        config = load_multi_asset_live_config(args.config, mode="observe")
        sources = discover_cohort_implementation_sources(
            _REPOSITORY_ROOT,
            args.backtest_lab_root.resolve(),
        )
        result = create_cohort_prestart_backup(
            config,
            implementation_sources=sources,
        )
        manifest = verify_cohort_prestart_backup(result.path)
        _require_report_only_manifest(manifest)
    except (
        CohortPrestartBackupError,
        FileNotFoundError,
        MultiAssetLiveConfigError,
        ValueError,
    ) as exc:
        print(f"pre-change backup refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_summary(config, result, manifest), sort_keys=True))
    return 0


def _require_report_only_manifest(manifest: Mapping[str, object]) -> None:
    if manifest.get("execution_authority") != "none":
        raise CohortPrestartBackupError(
            "pre-change backup manifest has execution authority"
        )


def _summary(
    config: MultiAssetLiveConfig,
    result: CohortPrestartBackupResult,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    return {
        "status": "verified",
        "purpose": "pre_change_implementation_baseline",
        "snapshot_mode": "observe",
        "live_run_identity_claimed": False,
        "bundle": str(result.path),
        "created_at_utc": manifest.get("created_at_utc"),
        "execution_authority": manifest.get("execution_authority"),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "strategy_changed_from_latest_ledger": result.strategy_changed,
        "manifest_sha256": result.manifest_sha256,
        "implementation_file_count": result.implementation_file_count,
        "implementation_sha256": result.implementation_sha256,
    }


if __name__ == "__main__":
    raise SystemExit(main())
