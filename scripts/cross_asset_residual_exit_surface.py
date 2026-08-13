#!/usr/bin/env python3
"""Run the bounded report-only residual stop/hold development surface."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
)
from hypervector.research.cross_asset_residual_data import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    load_residual_development_inputs,
)
from hypervector.research.cross_asset_residual_screen import (
    build_residual_exit_surface,
)
from hypervector.research.cross_asset_residual_provenance import (
    build_residual_generator_identity,
)

_HOLDS = (12, 36, 72, 144, 288)
_STOPS = (3.0, 4.0, 5.0)


def build_parser() -> argparse.ArgumentParser:
    """Return the bounded report-only surface parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id", default="cross_asset_residual_exit_surface_v2")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/cross_asset_residual_exit_surface_v2.json"),
    )
    parser.add_argument(
        "--trades-output",
        type=Path,
        default=Path(
            "data/logs/research/cross_asset_residual_exit_surface_v2.trades.parquet"
        ),
    )
    return parser


def declared_variants() -> tuple[tuple[str, CrossAssetResidualConfig], ...]:
    """Return all 15 globally shared stop/hold combinations."""
    base = CrossAssetResidualConfig()
    return tuple(
        (
            f"stop{stop:g}_hold{hold}",
            replace(base, stop_z=stop, maximum_hold_bars=hold),
        )
        for stop in _STOPS
        for hold in _HOLDS
    )


def main() -> int:
    """Evaluate and publish the complete frozen development surface."""
    args = build_parser().parse_args()
    _require_new_outputs(args.output, args.trades_output)
    frames, identity = load_residual_development_inputs(args.data_root)
    artifact, trades = build_residual_exit_surface(
        minute_frames=frames,
        variants=declared_variants(),
        run_id=args.run_id,
        start=DEVELOPMENT_START,
        end=DEVELOPMENT_END,
        source_identity=identity,
    )
    write_immutable_parquet(args.trades_output, trades)
    artifact["trade_storage"] = {
        "path": str(args.trades_output),
        **file_evidence(args.trades_output),
        "rows": len(trades),
    }
    artifact["generator_identity"] = build_residual_generator_identity(Path(__file__))
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


def _require_new_outputs(output: Path, trades_output: Path) -> None:
    for path in (output, trades_output):
        if path.exists():
            raise FileExistsError(f"immutable residual surface exists: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
