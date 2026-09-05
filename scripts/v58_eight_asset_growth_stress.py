#!/usr/bin/env python3
"""Publish report-only exact-roster V58 growth-stress evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from math import isclose, isfinite
from pathlib import Path
import sys

import duckdb

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_candidate_notionals import candidate_asset_notionals
from hypervector.research.cohort_execution_friction import collect_execution_friction
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)


_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_VENUE_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
_CORE_DEPTH = Path(
    "data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json"
)
_PREFLIGHT = Path(
    "data/logs/research/bidirectional_cohort/v58_eight_asset_preflight_20260818_v1.json"
)
_DATABASE = Path("data/research/market.duckdb")
_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_HIP3_DEPTH_PATHS = {
    "xyz:SP500": Path(
        "data/logs/research/"
        "xyz_sp500_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:SPCX": Path(
        "data/logs/research/"
        "xyz_spcx_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:SNDK": Path(
        "data/logs/research/"
        "xyz_sndk_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:BRENTOIL": Path(
        "data/logs/research/"
        "xyz_brentoil_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
}
_GENERATOR_PATHS = (
    Path("scripts/v58_eight_asset_growth_stress.py"),
    Path("src/hypervector/research/cohort_candidate_notionals.py"),
    Path("src/hypervector/research/cohort_execution_friction.py"),
    Path("src/hypervector/research/v43_portfolio_friction_stress.py"),
    Path("src/hypervector/live/cohort_entry_sizing.py"),
    Path("src/hypervector/live/multi_asset_live_config.py"),
    Path("src/hypervector/live/cohort_execution_plan.py"),
    Path("src/hypervector/data/oxa_storage.py"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)
Record = Mapping[str, object]
_CORE_DEPTH_SYMBOLS = ("BTC", "HYPE")
_VENUE_DEPTH_SYMBOLS = ("ETH", "SOL")
_SCHEMA_VERSION = "v58_eight_asset_growth_stress_v1"


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable V58 stress command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--venue-stress", type=Path, default=_VENUE_STRESS)
    parser.add_argument("--core-depth", type=Path, default=_CORE_DEPTH)
    parser.add_argument(
        "--sp500-depth", type=Path, default=_HIP3_DEPTH_PATHS["xyz:SP500"]
    )
    parser.add_argument(
        "--spcx-depth", type=Path, default=_HIP3_DEPTH_PATHS["xyz:SPCX"]
    )
    parser.add_argument(
        "--sndk-depth", type=Path, default=_HIP3_DEPTH_PATHS["xyz:SNDK"]
    )
    parser.add_argument(
        "--brentoil-depth", type=Path, default=_HIP3_DEPTH_PATHS["xyz:BRENTOIL"]
    )
    parser.add_argument("--preflight", type=Path, default=_PREFLIGHT)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def exact_depth_overrides(
    config: MultiAssetLiveConfig,
    *,
    equity_usd: float,
    core_document: Record,
    venue_document: Record,
    hip3_documents: Mapping[str, Record],
) -> tuple[dict[str, float], dict[str, object]]:
    """Bind every V58 asset to exact-target-notional p99 visible depth."""
    notionals = candidate_asset_notionals(config, equity_usd)
    expected = set(config.symbols)
    if set(hip3_documents).union(_CORE_DEPTH_SYMBOLS, _VENUE_DEPTH_SYMBOLS) != expected:
        raise ValueError("depth source symbols must exactly match the V58 roster")
    depths: dict[str, float] = {}
    sources: dict[str, object] = {}
    for symbol in _CORE_DEPTH_SYMBOLS:
        depths[symbol], sources[symbol] = _core_depth(
            core_document, symbol, notionals[symbol]
        )
    for symbol in _VENUE_DEPTH_SYMBOLS:
        depths[symbol], sources[symbol] = _venue_depth(
            venue_document, symbol, notionals[symbol]
        )
    for symbol, document in hip3_documents.items():
        depths[symbol], sources[symbol] = _hip3_depth(
            document, symbol, notionals[symbol]
        )
    return depths, {"notionals_usd": notionals, "sources": sources}


def validate_preflight(
    config: MultiAssetLiveConfig,
    preflight: Record,
    venue_document: Record,
) -> dict[str, object]:
    """Reconcile current venue identity, sizing, and fees to frozen stress."""
    identity = _mapping(preflight.get("identity"), "preflight identity")
    if identity.get("candidate_profile_id") != config.profile_id:
        raise ValueError("preflight candidate profile differs from V58")
    if identity.get("candidate_profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("preflight candidate fingerprint differs from V58")
    portfolio = _mapping(preflight.get("portfolio"), "preflight portfolio")
    _require_integer(portfolio.get("configured_assets"), len(config.assets), "assets")
    _require_integer(
        portfolio.get("maximum_positions"), config.maximum_positions, "positions"
    )
    margin = sum(asset.margin_fraction for asset in config.assets)
    _require_same_number(
        portfolio.get("maximum_configured_margin_fraction"), margin, "margin fraction"
    )
    equity = _positive_number(
        portfolio.get("sizing_reference_equity_usd"), "preflight equity"
    )
    notionals = candidate_asset_notionals(config, equity)
    current_fees = _preflight_assets(preflight, notionals)
    stress_fees = _stress_fees(venue_document, config.symbols)
    for symbol, current in current_fees.items():
        if current > stress_fees[symbol] + 1e-12:
            raise ValueError(f"current fee exceeds stress fee for {symbol}")
    return {
        "configured_assets": len(config.assets),
        "maximum_positions": config.maximum_positions,
        "maximum_configured_margin_fraction": margin,
        "sizing_reference_equity_usd": equity,
        "planned_notionals_usd": notionals,
        "current_one_way_taker_fee_bps": current_fees,
        "stress_one_way_taker_fee_bps": stress_fees,
        "fee_stress_conservative_for_current_inputs": True,
    }


def build_v58_report(
    config_path: Path,
    *,
    venue_stress_path: Path,
    friction: Mapping[str, Record],
    depths: Mapping[str, float],
    preflight_evidence: Record,
    depth_evidence: Record,
) -> dict[str, object]:
    """Build exact-roster stress while retaining all report-only boundaries."""
    report = build_v43_portfolio_friction_stress(
        config_path,
        venue_stress_path=venue_stress_path,
        execution_friction=friction,
        account_values_usd=(5_000.0,),
        schema_version=_SCHEMA_VERSION,
        visible_depth_p99_bps=depths,
    )
    report.update(
        {
            "v58_preflight_evidence": dict(preflight_evidence),
            "candidate_depth_evidence": dict(depth_evidence),
            "evidence_limitations": [
                "p99 components are marginal tails, not one joint probability",
                "visible depth and realized slippage can overlap economically",
                "stop gaps, outages, and book cancellation can exceed modeled loss",
                "route economics and co-trigger frequency are not established here",
            ],
        }
    )
    return report


def _preflight_assets(
    document: Record, notionals: Mapping[str, float]
) -> dict[str, float]:
    rows = document.get("assets")
    if not isinstance(rows, list):
        raise ValueError("preflight assets must be a list")
    indexed: dict[str, Record] = {}
    for value in rows:
        row = _mapping(value, "preflight asset")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol in indexed:
            raise ValueError("preflight asset symbols must be unique text")
        indexed[symbol] = row
    if set(indexed) != set(notionals):
        raise ValueError("preflight assets must exactly match V58")
    return {
        symbol: _preflight_asset(row, symbol, notionals[symbol])
        for symbol, row in indexed.items()
    }


def _preflight_asset(row: Record, symbol: str, notional: float) -> float:
    sizing = _mapping(row.get("sizing"), f"preflight sizing {symbol}")
    _require_same_notional(sizing.get("planned_notional_usd"), notional, symbol)
    venue = _mapping(row.get("venue"), f"preflight venue {symbol}")
    return _positive_number(
        venue.get("one_way_taker_fee_bps"), f"preflight fee {symbol}"
    )


def _stress_fees(document: Record, symbols: Sequence[str]) -> dict[str, float]:
    assets = _mapping(document.get("by_asset"), "venue stress assets")
    return {
        symbol: _positive_number(
            _mapping(assets.get(symbol), f"venue stress {symbol}").get(
                "round_trip_taker_fee_bps"
            ),
            f"stress round-trip fee {symbol}",
        )
        / 2.0
        for symbol in symbols
    }


def _core_depth(document: Record, symbol: str, notional: float) -> tuple[float, Record]:
    depth = _mapping(document.get("candidate_depth_evidence"), "core depth evidence")
    notionals = _mapping(depth.get("notionals_usd"), "core depth notionals")
    _require_same_notional(notionals.get(symbol), notional, symbol)
    assets = _mapping(depth.get("assets"), "core depth assets")
    asset = _mapping(assets.get(symbol), f"core depth {symbol}")
    profile = _mapping(asset.get("profile"), f"core depth profile {symbol}")
    p99, count = _two_side_p99(profile, symbol)
    return p99, {"source": "bounded_live_l2", "sample_count": count}


def _venue_depth(
    document: Record, symbol: str, notional: float
) -> tuple[float, Record]:
    sizing = _mapping(document.get("sizing_plan"), "venue sizing plan")
    _require_same_notional(
        sizing.get("planned_notional_usd_per_slot"), notional, symbol
    )
    assets = _mapping(document.get("by_asset"), "venue by_asset")
    asset = _mapping(assets.get(symbol), f"venue depth {symbol}")
    p99 = _mapping(asset.get("p99"), f"venue p99 {symbol}")
    value = _positive_number(p99.get("adverse_exit_visible_cost_bps"), symbol)
    return value, {"source": "frozen_exact_notional_venue_stress"}


def _hip3_depth(document: Record, symbol: str, notional: float) -> tuple[float, Record]:
    profile = _mapping(document.get("profile"), f"HIP-3 profile {symbol}")
    if profile.get("symbol") != symbol:
        raise ValueError(f"HIP-3 depth symbol differs for {symbol}")
    rows = profile.get("notionals")
    if not isinstance(rows, list):
        raise ValueError(f"HIP-3 depth notionals must be a list for {symbol}")
    matches = [row for row in rows if _notional_matches(row, notional)]
    if len(matches) != 1:
        raise ValueError(f"HIP-3 depth needs one exact notional for {symbol}")
    row = _mapping(matches[0], f"HIP-3 depth row {symbol}")
    p99, count = _two_side_p99(row, symbol)
    return p99, {
        "source": "historical_0xarchive",
        "sample_count": count,
        "both_complete_rate": _unit_interval(row.get("both_complete_rate"), symbol),
    }


def _two_side_p99(row: Record, symbol: str) -> tuple[float, int]:
    values: list[float] = []
    counts: list[int] = []
    for side in ("buy", "sell"):
        data = _mapping(row.get(f"{side}_visible_cost_bps"), f"{symbol} {side} depth")
        values.append(_positive_number(data.get("p99"), f"{symbol} {side}"))
        counts.append(_positive_integer(data.get("count"), f"{symbol} {side}"))
    return max(values), min(counts)


def _notional_matches(value: object, expected: float) -> bool:
    if not isinstance(value, Mapping):
        return False
    raw = value.get("notional_usd")
    return (
        isinstance(raw, (int, float))
        and not isinstance(raw, bool)
        and isclose(float(raw), expected, rel_tol=0.0, abs_tol=1e-9)
    )


def _require_same_notional(value: object, expected: float, symbol: str) -> None:
    actual = _positive_number(value, f"{symbol} depth notional")
    if not isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"depth notional differs for {symbol}: {actual} != {expected}")


def _require_same_number(value: object, expected: float, label: str) -> None:
    actual = _positive_number(value, label)
    if not isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{label} differs: {actual} != {expected}")


def _require_integer(value: object, expected: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ValueError(f"preflight {label} differs: {value} != {expected}")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _unit_interval(value: object, label: str) -> float:
    result = _positive_number(value, f"{label} complete rate")
    if result > 1.0:
        raise ValueError(f"{label} complete rate must not exceed one")
    return result


def run(args: argparse.Namespace) -> int:
    """Reconcile exact sources and publish one immutable report-only artifact."""
    paths = _static_input_paths(args)
    initial = _input_evidence(paths)
    config = load_multi_asset_live_config(args.config, mode="observe")
    core, venue, hip3, preflight = _source_documents(args)
    depths, depth_evidence = exact_depth_overrides(
        config,
        equity_usd=5_000.0,
        core_document=core,
        venue_document=venue,
        hip3_documents=hip3,
    )
    preflight_evidence = validate_preflight(config, preflight, venue)
    friction, execution_evidence = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    report = build_v58_report(
        args.config,
        venue_stress_path=args.venue_stress,
        friction=friction,
        depths=depths,
        preflight_evidence=preflight_evidence,
        depth_evidence=depth_evidence,
    )
    final_friction, final_execution = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    if (friction, execution_evidence) != (final_friction, final_execution):
        raise RuntimeError("V58 execution evidence changed during evaluation")
    if initial != _input_evidence(paths):
        raise RuntimeError("V58 static evidence changed during evaluation")
    report.update(_publication_payload(initial, friction, execution_evidence))
    write_immutable_json(args.output, report)
    return 0


def _source_documents(
    args: argparse.Namespace,
) -> tuple[Record, Record, dict[str, Record], Record]:
    """Load the bounded JSON sources used by one report."""
    hip3 = {
        "xyz:SP500": _load_json(args.sp500_depth, "SP500 depth"),
        "xyz:SPCX": _load_json(args.spcx_depth, "SPCX depth"),
        "xyz:SNDK": _load_json(args.sndk_depth, "SNDK depth"),
        "xyz:BRENTOIL": _load_json(args.brentoil_depth, "BRENTOIL depth"),
    }
    return (
        _load_json(args.core_depth, "core depth"),
        _load_json(args.venue_stress, "venue stress"),
        hip3,
        _load_json(args.preflight, "V58 preflight"),
    )


def _static_input_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    """Return every immutable file input except the reconciled DuckDB projection."""
    return (
        args.config,
        args.venue_stress,
        args.core_depth,
        args.sp500_depth,
        args.spcx_depth,
        args.sndk_depth,
        args.brentoil_depth,
        args.preflight,
        args.checkpoint,
        *_GENERATOR_PATHS,
    )


def _input_evidence(paths: Sequence[Path]) -> dict[str, object]:
    """Hash every bounded static input and generator dependency."""
    return {str(path): {"path": str(path), **file_evidence(path)} for path in paths}


def _publication_payload(
    inputs: Record,
    friction: Mapping[str, Record],
    execution_evidence: Record,
) -> dict[str, object]:
    """Attach immutable provenance without adding strategy authority."""
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": dict(inputs),
        "execution_friction_evidence": dict(friction),
        "source_execution_evidence": dict(execution_evidence),
    }


def _load_json(path: Path, label: str) -> Record:
    """Load one JSON object or fail with source context."""
    return _mapping(json.loads(path.read_text(encoding="utf-8")), label)


def main(argv: Sequence[str] | None = None) -> int:
    """Return a bounded nonzero error without exposing execution authority."""
    try:
        return run(build_parser().parse_args(argv))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
        duckdb.Error,
    ) as exc:
        print(f"V58 eight-asset growth stress failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
