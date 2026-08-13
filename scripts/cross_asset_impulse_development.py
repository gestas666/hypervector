#!/usr/bin/env python3
"""Publish one frozen report-only cross-asset impulse development screen."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research import cross_asset_impulse_screen as impulse_screen
from hypervector.research.cross_asset_impulse_artifact_validation import (
    validate_cross_asset_impulse_artifact,
)
from hypervector.research.cross_asset_impulse_data import (
    load_impulse_development_inputs,
)
from hypervector.research.cross_asset_impulse_models import CrossAssetImpulseConfig
from hypervector.research.cross_asset_impulse_provenance import (
    build_impulse_generator_identity,
    build_prior_residual_identity,
)

_SCHEMA = "cross_asset_impulse_development_v1"
_PRIMARY_CELLS = 15
_SYMBOLS = {"BTC", "ETH", "SOL", "HYPE"}


def build_parser() -> argparse.ArgumentParser:
    """Return the frozen report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id", default="cross_asset_impulse_development_v1")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/cross_asset_impulse_development_v1.json"),
    )
    parser.add_argument(
        "--events-output",
        type=Path,
        default=Path(
            "data/logs/research/cross_asset_impulse_development_v1.events.parquet"
        ),
    )
    parser.add_argument(
        "--prior-residual",
        type=Path,
        default=Path("data/logs/research/cross_asset_residual_exit_surface_v2.json"),
    )
    return parser


def run_development(
    *,
    data_root: Path,
    run_id: str,
    output: Path,
    events_output: Path,
    prior_residual: Path,
    runner_path: Path,
) -> None:
    """Build and immutably publish one complete development evidence pair."""
    _require_new_outputs(output, events_output)
    config = CrossAssetImpulseConfig()
    prior_identity = build_prior_residual_identity(prior_residual)
    frames, identity = load_impulse_development_inputs(data_root, config)
    artifact, event_rows = impulse_screen.build_impulse_development(
        minute_frames=frames,
        config=config,
        run_id=run_id,
        source_identity=identity,
        prior_search_identity=prior_identity,
    )
    _validate_screen_artifact(artifact)
    if artifact["source_identity"] != identity:
        raise ValueError("impulse screen changed the source identity")
    _validate_event_rows(event_rows)
    generator_identity = build_impulse_generator_identity(runner_path)
    write_immutable_parquet(events_output, event_rows)
    artifact["event_storage"] = {
        "path": str(events_output),
        **file_evidence(events_output),
        "rows": len(event_rows),
    }
    artifact["generator_identity"] = generator_identity
    artifact["prior_cross_asset_search"] = prior_identity
    artifact["contract_identity"] = _contract_identity(config)
    write_immutable_json(output, artifact)
    validate_cross_asset_impulse_artifact(output)


def _validate_screen_artifact(artifact: dict[str, object]) -> None:
    expected = {
        "schema_version": _SCHEMA,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(artifact.get(key) != value for key, value in expected.items()):
        raise ValueError("impulse screen artifact violates report-only identity")
    if artifact.get("searched_set_count") != _PRIMARY_CELLS:
        raise ValueError("impulse screen searched-set count must equal 15")
    identity = artifact.get("source_identity")
    if not isinstance(identity, dict) or set(identity) != _SYMBOLS:
        raise ValueError("impulse screen source identity must cover four symbols")
    if any(not _has_source_hash(value) for value in identity.values()):
        raise ValueError("impulse screen source identity is missing a bars hash")


def _has_source_hash(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    bars = value.get("bars")
    return isinstance(bars, dict) and isinstance(bars.get("sha256"), str)


def _validate_event_rows(rows: pd.DataFrame) -> None:
    required = {"report_only", "execution_authority"}
    if not required.issubset(rows.columns):
        raise ValueError("impulse event rows are missing authority columns")
    if not rows["execution_authority"].eq("none").all():
        raise ValueError("impulse event rows contain execution authority")
    if not rows["report_only"].eq(True).all():
        raise ValueError("impulse event rows must be report-only")


def _contract_identity(config: CrossAssetImpulseConfig) -> dict[str, object]:
    return {
        "warmup_start_utc": config.warmup_start.isoformat(),
        "development_start_utc": config.development_start.isoformat(),
        "development_end_utc": config.development_end.isoformat(),
        "report_only": config.report_only,
        "execution_authority": config.execution_authority,
    }


def _require_new_outputs(output: Path, events_output: Path) -> None:
    for path in (output, events_output):
        if path.exists():
            raise FileExistsError(f"immutable impulse output exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and publish one evidence artifact."""
    args = build_parser().parse_args(argv)
    run_development(
        data_root=args.data_root,
        run_id=args.run_id,
        output=args.output,
        events_output=args.events_output,
        prior_residual=args.prior_residual,
        runner_path=Path(__file__),
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
