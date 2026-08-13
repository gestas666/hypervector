"""Immutable command boundary for the HYPE five-minute impulse study."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hype_impulse_5m_candidate import (
    aggregate_completed_five_minute_bars,
)
from hypervector.research.hype_impulse_5m_study import build_study_report

_DEFAULT_NOMINAL_COST_BPS = 13.0
_DEFAULT_STRESS_COST_BPS = 26.7616739042848


def main(arguments: Sequence[str] | None = None) -> int:
    """Build and publish one source-bound, report-only study artifact."""
    args = _parser().parse_args(arguments)
    candles = Path(args.candles).resolve()
    funding = Path(args.funding).resolve()
    output = Path(args.out).resolve()
    source_paths = _source_paths()
    before = _identities((candles, funding, *source_paths))
    minute = pd.read_parquet(candles)
    funding_frame = _funding_frame(pd.read_parquet(funding))
    bars = aggregate_completed_five_minute_bars(minute)
    rates = pd.Series(
        funding_frame["funding_rate"].to_numpy(),
        index=pd.DatetimeIndex(funding_frame["timestamp"]),
    )
    report = build_study_report(
        bars,
        rates,
        nominal_cost_bps=args.nominal_cost_bps,
        stress_cost_bps=args.stress_cost_bps,
    )
    _require_unchanged(before)
    report.update(_provenance(before, candles, funding, bars, funding_frame))
    write_immutable_json(output, report)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", required=True)
    parser.add_argument("--funding", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--nominal-cost-bps", type=float, default=_DEFAULT_NOMINAL_COST_BPS
    )
    parser.add_argument(
        "--stress-cost-bps", type=float, default=_DEFAULT_STRESS_COST_BPS
    )
    return parser


def _funding_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "funding_rate", "source", "event_ts_ms"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"HYPE funding evidence missing columns: {missing}")
    result = frame.loc[:, sorted(required)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    if not result["source"].eq("hl_funding_history").all():
        raise ValueError("HYPE funding evidence must use hl_funding_history")
    if (
        result["timestamp"].duplicated().any()
        or not result["timestamp"].is_monotonic_increasing
    ):
        raise ValueError("HYPE funding timestamps must be ordered and unique")
    return result


def _provenance(
    identities: dict[Path, dict[str, object]],
    candles: Path,
    funding: Path,
    bars: pd.DataFrame,
    funding_frame: pd.DataFrame,
) -> dict[str, object]:
    sources = [path for path in identities if path not in {candles, funding}]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": [identities[path] for path in sources],
        "input_summary": {
            "completed_5m_bars": len(bars),
            "gap_filled_5m_bars": int(bars["contains_gap_fill"].sum()),
            "hourly_funding_rows": len(funding_frame),
        },
        "inputs": {
            "candles": identities[candles],
            "funding": identities[funding],
        },
    }


def _source_paths() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[3]
    return (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hype_impulse_5m_candidate.py",
        root / "src/hypervector/research/hype_impulse_5m_signals.py",
        root / "src/hypervector/research/hype_impulse_5m_study.py",
    )


def _identities(paths: tuple[Path, ...]) -> dict[Path, dict[str, object]]:
    result: dict[Path, dict[str, object]] = {}
    for path in paths:
        data = path.read_bytes()
        result[path] = {
            "bytes": len(data),
            "path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return result


def _require_unchanged(expected: dict[Path, dict[str, object]]) -> None:
    observed = _identities(tuple(expected))
    if observed != expected:
        raise RuntimeError(
            "HYPE impulse study input or generator changed during evaluation"
        )
