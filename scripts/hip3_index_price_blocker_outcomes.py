#!/usr/bin/env python3
"""Publish exact report-only outcomes for live HIP-3 price blockers."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import cast

import pandas as pd

from hypervector.data.hip3_public_candles import (
    Hip3CandleSourceProtocol,
    Hip3PublicCandleSource,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_index_price_blocker_outcomes import (
    build_hip3_index_price_blocker_outcomes,
)

Record = dict[str, object]
_DEFAULT_HORIZONS = (15, 30, 60)
_BAR_MS = 900_000


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only outcome parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition-report", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--side", choices=("long", "short"), required=True)
    parser.add_argument("--observed-at-utc", required=True)
    parser.add_argument(
        "--horizon-minutes",
        type=int,
        action="append",
        dest="horizons",
    )
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    candle_source: Hip3CandleSourceProtocol | None = None,
) -> Record:
    """Publish one immutable current-run price-blocker outcome report."""
    paths = _paths(args)
    exact = {key: file_evidence(path) for key, path in paths.items()}
    condition = _json_object(paths["condition_report"], "condition report")
    checkpoint = _json_object(paths["checkpoint"], "checkpoint")
    scope = _mapping(condition, "scope")
    cost = _runtime_cost(checkpoint, scope)
    observed_ms = _utc_ms(str(args.observed_at_utc))
    candles = _completed_candles(
        _candles(candle_source, condition, scope, observed_ms), observed_ms
    )
    report = build_hip3_index_price_blocker_outcomes(
        condition_report=condition,
        candles=candles,
        side=str(args.side),
        horizons_minutes=tuple(args.horizons or _DEFAULT_HORIZONS),
        round_trip_friction_bps=_number(cost, "round_trip_friction_bps"),
        stop_bps=_number(cost, "stop_bps"),
    )
    report["cost_evidence"] = cost
    report["market_candle_evidence"] = _market_evidence(candles, observed_ms)
    report["input_evidence"] = _input_evidence(paths, exact)
    report["generator_identity"] = _generator_identity()
    _require_unchanged_condition(paths["condition_report"], exact["condition_report"])
    write_immutable_json(Path(args.output), report)
    return report


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {
        "condition_report": Path(args.condition_report),
        "checkpoint": Path(args.checkpoint),
    }
    if len(set(paths.values())) != len(paths):
        raise ValueError("price-blocker input paths must be distinct")
    return paths


def _runtime_cost(
    checkpoint: Mapping[str, object], scope: Mapping[str, object]
) -> Record:
    _validate_checkpoint_identity(checkpoint, scope)
    audit = _mapping(checkpoint, "audit")
    execution = _mapping(audit, "execution")
    parity = _mapping(execution, "friction_parity")
    routes = _mapping(parity, "by_provider_symbol")
    route = f"{_text(scope, 'provider_id')}|{_text(scope, 'symbol')}"
    row = _mapping(routes, route)
    if row.get("parity_state") != "runtime_shape_aligned":
        raise ValueError("price-blocker route friction is not runtime aligned")
    modeled = _mapping(row, "modeled_contract")
    runtime = _mapping(row, "runtime_contract")
    fee = _number(modeled, "entry_fee_bps")
    slippage = _number(modeled, "entry_slippage_bps")
    stop = _number(runtime, "stop_bps")
    if stop != _number(scope, "execution_stop_bps"):
        raise ValueError("price-blocker stop differs from frozen condition report")
    return {
        "route": route,
        "status": "symmetric_modeled_sensitivity",
        "entry_fee_bps": fee,
        "entry_slippage_bps": slippage,
        "round_trip_friction_bps": 2.0 * (fee + slippage),
        "stop_bps": stop,
        "source": _text(modeled, "evidence_source"),
        "observed_fills": 0,
    }


def _validate_checkpoint_identity(
    checkpoint: Mapping[str, object], scope: Mapping[str, object]
) -> None:
    contract = _mapping(checkpoint, "checkpoint_contract")
    generation = _mapping(checkpoint, "configuration_generation")
    run = _mapping(_mapping(checkpoint, "audit"), "run")
    expected_fingerprint = _text(scope, "profile_fingerprint")
    valid = (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("runtime_strategy_changed") is False
        and generation.get("state") == "current_runtime_configuration"
        and generation.get("matches_runtime") is True
        and generation.get("current_profile_fingerprint") == expected_fingerprint
        and generation.get("runtime_profile_fingerprint") == expected_fingerprint
        and run.get("run_id") == scope.get("run_id")
        and run.get("profile_id") == scope.get("profile_id")
        and run.get("profile_fingerprint") == expected_fingerprint
    )
    if not valid:
        raise ValueError("price-blocker checkpoint identity is not exact")


def _candles(
    source: Hip3CandleSourceProtocol | None,
    condition: Mapping[str, object],
    scope: Mapping[str, object],
    observed_ms: int,
) -> pd.DataFrame:
    rows = condition.get("observations")
    if not isinstance(rows, list) or not rows:
        raise ValueError("price-blocker condition observations must be non-empty")
    boundaries = [
        _integer(_object(row, "condition observation"), "decision_time_ms")
        for row in rows
    ]
    start_ms = min(boundaries)
    if observed_ms <= start_ms:
        raise ValueError("price-blocker observed time must follow first decision")
    return (source or Hip3PublicCandleSource()).completed_candles(
        symbol=_text(scope, "symbol"),
        start_ms=start_ms,
        end_ms=observed_ms,
        observed_at_ms=observed_ms,
    )


def _market_evidence(frame: pd.DataFrame, observed_ms: int) -> Record:
    required = ("timestamp", "open", "high", "low", "close")
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"price-blocker market evidence missing: {sorted(missing)}")
    rows = []
    for raw in frame.loc[:, list(required)].itertuples(index=False, name=None):
        timestamp = pd.Timestamp(raw[0])
        rows.append(
            {
                "timestamp_ms": int(timestamp.timestamp() * 1_000),
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
            }
        )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "source": "hyperliquid_public_candle_snapshot_15m",
        "observed_at_ms": observed_ms,
        "rows": len(rows),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "candles": rows,
    }


def _completed_candles(frame: pd.DataFrame, observed_ms: int) -> pd.DataFrame:
    if "timestamp" not in frame.columns:
        raise ValueError("price-blocker candles missing timestamp")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    completed = timestamps.map(lambda value: int(value.timestamp() * 1_000) + _BAR_MS)
    return frame.loc[completed <= observed_ms].reset_index(drop=True)


def _input_evidence(paths: Mapping[str, Path], exact: Mapping[str, Record]) -> Record:
    return {
        key: {"path": str(path.resolve()), **exact[key]} for key, path in paths.items()
    }


def _require_unchanged_condition(path: Path, expected: Mapping[str, object]) -> None:
    if file_evidence(path) != expected:
        raise RuntimeError("price-blocker condition report changed during evaluation")


def _generator_identity() -> Record:
    root = Path(__file__).parents[1]
    paths = (
        Path(__file__),
        root / "src/hypervector/research/hip3_index_price_blocker_outcomes.py",
        root / "src/hypervector/data/hip3_public_candles.py",
        root / "pyproject.toml",
        root / "uv.lock",
    )
    return {
        "files": [
            {"path": str(path.resolve()), **file_evidence(path)} for path in paths
        ]
    }


def _json_object(path: Path, label: str) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Record, value)


def _mapping(row: Mapping[str, object], key: str) -> Record:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"price-blocker {key} must be an object")
    return dict(value)


def _object(value: object, label: str) -> Record:
    if not isinstance(value, dict):
        raise ValueError(f"price-blocker {label} must be an object")
    return dict(value)


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"price-blocker {key} must be text")
    return value.strip()


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"price-blocker {key} must be an integer")
    return value


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"price-blocker {key} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"price-blocker {key} must be finite and nonnegative")
    return result


def _utc_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("price-blocker observed time must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only outcome command."""
    report = run_command(build_parser().parse_args(argv))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
