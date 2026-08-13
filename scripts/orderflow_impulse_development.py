#!/usr/bin/env python3
"""Run the immutable BTC/SOL 1m venue-native order-flow development screen."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.research.orderflow_impulse_contract import (
    default_orderflow_impulse_config,
)
from hypervector.research.orderflow_impulse_experiment import (
    run_orderflow_impulse_experiment,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only experiment and publish immutable evidence files."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    sidecar = output.with_suffix(".parquet")
    _ensure_available(output, sidecar)
    result = run_orderflow_impulse_experiment(
        Path(args.database),
        _timestamp(str(args.start)),
        _timestamp(str(args.end)),
        {"BTC": Path(args.btc_funding), "SOL": Path(args.sol_funding)},
        default_orderflow_impulse_config(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.outcomes.to_parquet(sidecar, index=False)
    report = {
        **result.report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "sidecar": {
            "path": str(sidecar),
            "sha256": _file_sha256(sidecar),
            "rows": len(result.outcomes),
        },
    }
    output.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only order-flow impulse artifact: {output}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--btc-funding", required=True, type=Path)
    parser.add_argument("--sol-funding", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("order-flow timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _ensure_available(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"order-flow outputs already exist: {existing}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
