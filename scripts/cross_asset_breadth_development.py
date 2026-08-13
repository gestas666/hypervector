#!/usr/bin/env python3
"""Publish one frozen report-only BTC breadth-expansion development screen."""

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
from hypervector.research.cross_asset_breadth_artifact_validation import (
    validate_cross_asset_breadth_artifact,
)
from hypervector.research.cross_asset_breadth_data import (
    load_breadth_development_inputs,
)
from hypervector.research.cross_asset_breadth_models import CrossAssetBreadthConfig
from hypervector.research.cross_asset_breadth_provenance import (
    build_breadth_generator_identity,
    build_prior_impulse_identity,
)
from hypervector.research.cross_asset_breadth_screen import (
    build_breadth_development,
)

_DEFAULT_OUTPUT = Path("data/logs/research/cross_asset_breadth_development_v1.json")
_DEFAULT_EVENTS = Path(
    "data/logs/research/cross_asset_breadth_development_v1.events.parquet"
)
_DEFAULT_PRIOR = Path("data/logs/research/cross_asset_impulse_development_v1.json")


def build_parser() -> argparse.ArgumentParser:
    """Return the frozen report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id", default="cross_asset_breadth_development_v1")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--events-output", type=Path, default=_DEFAULT_EVENTS)
    parser.add_argument("--prior-impulse", type=Path, default=_DEFAULT_PRIOR)
    return parser


def run_development(
    *,
    data_root: Path,
    run_id: str,
    output: Path,
    events_output: Path,
    prior_impulse: Path,
    runner_path: Path,
) -> None:
    """Build and immutably publish one complete breadth evidence pair."""
    _require_new_outputs(output, events_output)
    config = CrossAssetBreadthConfig()
    prior = build_prior_impulse_identity(prior_impulse)
    inputs = load_breadth_development_inputs(data_root, config)
    artifact, event_rows = build_breadth_development(
        closes_15m=inputs.closes_15m,
        validity_15m=inputs.validity_15m,
        btc_minute_frame=inputs.minute_frames["BTC"],
        config=config,
        run_id=run_id,
        source_identity=inputs.source_identity,
        prior_search_identity=prior,
    )
    _validate_screen_artifact(artifact)
    _validate_event_rows(event_rows)
    write_immutable_parquet(events_output, event_rows)
    artifact["event_storage"] = {
        "path": str(events_output),
        **file_evidence(events_output),
        "rows": len(event_rows),
    }
    artifact["generator_identity"] = build_breadth_generator_identity(runner_path)
    artifact["prior_cross_asset_search"] = prior
    artifact["contract_identity"] = _contract_identity(config)
    write_immutable_json(output, artifact)
    validate_cross_asset_breadth_artifact(output)


def _validate_screen_artifact(artifact: dict[str, object]) -> None:
    expected = {
        "schema_version": "cross_asset_breadth_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "searched_set_count": 1,
    }
    if any(artifact.get(key) != value for key, value in expected.items()):
        raise ValueError("breadth screen artifact violates its frozen identity")
    identity = artifact.get("source_identity")
    if not isinstance(identity, dict) or tuple(identity) != (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
    ):
        raise ValueError("breadth source identity must cover four ordered symbols")


def _validate_event_rows(rows: pd.DataFrame) -> None:
    required = {"report_only", "execution_authority"}
    if rows.empty or not required.issubset(rows.columns):
        raise ValueError("breadth event rows are empty or missing authority")
    if (
        not rows["report_only"].eq(True).all()
        or not rows["execution_authority"].eq("none").all()
    ):
        raise ValueError("breadth event rows contain execution authority")


def _contract_identity(config: CrossAssetBreadthConfig) -> dict[str, object]:
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
            raise FileExistsError(f"immutable breadth output exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and publish one evidence artifact."""
    args = build_parser().parse_args(argv)
    run_development(
        data_root=args.data_root,
        run_id=args.run_id,
        output=args.output,
        events_output=args.events_output,
        prior_impulse=args.prior_impulse,
        runner_path=Path(__file__),
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
