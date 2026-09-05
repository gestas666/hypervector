#!/usr/bin/env python3
"""Run and atomically publish the frozen EMA-speed development screen."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.ema_speed_continuation_experiment import (
    run_ema_speed_development,
)


_DATABASE = Path("data/research/market.duckdb")
_BTC_FUNDING = (
    Path(
        "data/cache/vendor/hyperliquid/BTC/"
        "20250301T000000000000Z_20250728T000000000000Z_funding/funding.parquet"
    ),
    Path(
        "data/cache/vendor/hyperliquid/BTC/"
        "20250728T000000000000Z_20260428T000000000000Z_funding/funding.parquet"
    ),
    Path(
        "data/cache/vendor/hyperliquid/BTC/"
        "20260428T000000000000Z_20260727T000000000000Z_funding/funding.parquet"
    ),
)
_SOL_FUNDING = (
    Path(
        "data/cache/vendor/hyperliquid/SOL/"
        "20250301T000000000000Z_20250728T000000000000Z_funding/funding.parquet"
    ),
    Path(
        "data/cache/vendor/hyperliquid/SOL/"
        "20250728T000000000000Z_20260731T000000000000Z_funding/funding.parquet"
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the local report-only command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def publish_bundle(
    out_dir: Path,
    report: dict[str, object],
    trades: pd.DataFrame,
) -> None:
    """Publish report, lifecycle sidecar, and hashes as one immutable directory."""
    if out_dir.exists():
        raise FileExistsError(f"EMA-speed bundle output exists: {out_dir}")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".ema-speed-", dir=out_dir.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        report_path = stage / "report.json"
        trades_path = stage / "trades.parquet"
        report_path.write_text(_json(report), encoding="utf-8")
        trades.to_parquet(trades_path, index=False)
        manifest = _manifest(report_path, trades_path)
        (stage / "manifest.json").write_text(_json(manifest), encoding="utf-8")
        os.replace(stage, out_dir)


def _manifest(report_path: Path, trades_path: Path) -> dict[str, object]:
    return {
        "schema_version": "ema_speed_continuation_bundle_v1",
        "execution_authority": "none",
        "report_only": True,
        "files": {
            "report.json": file_evidence(report_path),
            "trades.parquet": file_evidence(trades_path),
        },
    }


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> None:
    """Run the frozen development scope and publish no execution authority."""
    args = build_parser().parse_args()
    result = run_ema_speed_development(
        args.database,
        {"BTC": _BTC_FUNDING, "SOL": _SOL_FUNDING},
    )
    publish_bundle(args.out_dir, result.report, result.trades)
    print(
        json.dumps(
            {
                "ok": True,
                "out_dir": str(args.out_dir),
                "assessment": result.report["assessment"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
