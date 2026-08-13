#!/usr/bin/env python3
"""Publish immutable candidate-notional depth and v45 stop-wave stress."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Literal

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_monitor_identity import active_ledger_identity
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_growth_sizing_evidence import (
    hip3_visible_quantiles,
)
from hypervector.research.cohort_recent_liquidity import (
    build_recent_liquidity_profile,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)

Record = Mapping[str, object]
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)
_ACTIVE = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_FRICTION = Path(
    "data/logs/research/bidirectional_cohort/"
    "v44_portfolio_friction_stress_20260811_v1.json"
)
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
_SP500_DEPTH = Path(
    "data/logs/research/xyz_sp500_liquidity_profile_notional750_1250_1750_20260810.json"
)
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/v45_growth_sizing_stress_20260812_v1.json"
)
_GENERATOR_PATHS = (
    Path("scripts/v45_growth_sizing_stress.py"),
    Path("src/hypervector/research/v43_portfolio_friction_stress.py"),
    Path("src/hypervector/research/cohort_growth_sizing_evidence.py"),
    Path("src/hypervector/research/cohort_recent_liquidity.py"),
    Path("src/hypervector/research/live_ledger_snapshot.py"),
    Path("src/hypervector/live/cohort_entry_sizing.py"),
    Path("src/hypervector/live/cohort_monitor_identity.py"),
    Path("src/hypervector/live/multi_asset_live_config.py"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable v45 report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-config", type=Path, default=_CANDIDATE)
    parser.add_argument("--active-config", type=Path, default=_ACTIVE)
    parser.add_argument("--friction", type=Path, default=_FRICTION)
    parser.add_argument("--venue-stress", type=Path, default=_VENUE)
    parser.add_argument("--sp500-depth", type=Path, default=_SP500_DEPTH)
    parser.add_argument(
        "--sp500-depth-source",
        choices=("archive", "live"),
        default="archive",
    )
    parser.add_argument("--account-values", type=float, nargs="+", default=[500, 5000])
    parser.add_argument("--depth-equity", type=float, default=5_000.0)
    parser.add_argument("--maximum-snapshots", type=int, default=240)
    parser.add_argument("--schema-version", default="v45_portfolio_friction_stress_v1")
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def candidate_asset_notionals(
    config: MultiAssetLiveConfig, account_value_usd: float
) -> dict[str, float]:
    """Return each asset's largest executable route notional at one equity."""
    output: dict[str, float] = {}
    for asset in config.assets:
        values = []
        for provider in config.providers:
            if asset.symbol not in provider.symbols:
                continue
            sizing = provider.entry_sizing(asset.symbol) or CohortEntrySizing(
                asset.margin_fraction, asset.max_notional_usd
            )
            values.append(
                sizing.planned_notional(
                    account_value_usd=account_value_usd,
                    leverage=asset.leverage,
                )
            )
        if not values:
            raise ValueError(f"candidate asset has no route: {asset.symbol}")
        output[asset.symbol] = max(values)
    return output


def collect_candidate_depth(
    candidate: MultiAssetLiveConfig,
    active: MultiAssetLiveConfig,
    *,
    account_value_usd: float,
    maximum_snapshots: int,
    sp500_depth_path: Path,
    sp500_depth_source: Literal["archive", "live"] = "archive",
) -> tuple[dict[str, float], dict[str, object]]:
    """Measure exact candidate-size p99 visible costs from frozen sources."""
    identity = active_ledger_identity(active)
    notionals = candidate_asset_notionals(candidate, account_value_usd)
    active_assets = {asset.symbol: asset for asset in active.assets}
    depths: dict[str, float] = {}
    evidence: dict[str, object] = {}
    for symbol in candidate.symbols:
        if symbol == "xyz:SP500" and sp500_depth_source == "archive":
            depth, source = _sp500_depth(sp500_depth_path, notionals[symbol])
        else:
            depth, source = _live_depth(
                active_assets[symbol],
                identity.run_id,
                notionals[symbol],
                maximum_snapshots,
            )
        depths[symbol] = depth
        evidence[symbol] = source
    return depths, {"notionals_usd": notionals, "assets": evidence}


def _live_depth(
    asset: object, run_id: str, notional: float, maximum_snapshots: int
) -> tuple[float, dict[str, object]]:
    ledger = getattr(asset, "live_ledger")
    with snapshot_decision_ledger(
        ledger, run_id=run_id, allow_incomplete_tail=True
    ) as (records, source):
        profile = build_recent_liquidity_profile(
            records,
            run_id=run_id,
            symbol=getattr(asset, "symbol"),
            profile_id=getattr(asset, "profile_id"),
            profile_fingerprint=getattr(asset, "profile_fingerprint"),
            notional_usd=notional,
            maximum_snapshots=maximum_snapshots,
        )
    p99 = max(_p99(profile, "buy"), _p99(profile, "sell"))
    return p99, {"source": "bounded_live_l2", "ledger": source, "profile": profile}


def _sp500_depth(path: Path, notional: float) -> tuple[float, dict[str, object]]:
    document = _load(path, "SP500 depth")
    quantiles = hip3_visible_quantiles(document, notional_usd=notional)
    return quantiles.p99, {
        "source": "historical_0xarchive",
        "file": {"path": str(path), **file_evidence(path)},
        "sample_count": quantiles.sample_count,
        "complete_rate": quantiles.complete_rate,
    }


def run(args: argparse.Namespace) -> int:
    """Build and publish one immutable report without execution authority."""
    paths = (
        args.candidate_config,
        args.active_config,
        args.friction,
        args.venue_stress,
        args.sp500_depth,
        *_GENERATOR_PATHS,
    )
    initial = _input_evidence(paths)
    candidate = load_multi_asset_live_config(args.candidate_config, mode="observe")
    active = load_multi_asset_live_config(args.active_config, mode="observe")
    depths, depth_evidence = collect_candidate_depth(
        candidate,
        active,
        account_value_usd=args.depth_equity,
        maximum_snapshots=args.maximum_snapshots,
        sp500_depth_path=args.sp500_depth,
        sp500_depth_source=args.sp500_depth_source,
    )
    friction = _load(args.friction, "execution friction")
    report = build_v43_portfolio_friction_stress(
        args.candidate_config,
        venue_stress_path=args.venue_stress,
        execution_friction=_mapping(
            friction.get("execution_friction_evidence"), "execution friction rows"
        ),
        account_values_usd=args.account_values,
        schema_version=args.schema_version,
        visible_depth_p99_bps=depths,
    )
    if initial != _input_evidence(paths):
        raise RuntimeError("v45 sizing evidence changed during evaluation")
    leverage = _configured_leverage(candidate)
    report.update(
        _publication_payload(initial, depth_evidence, args.depth_equity, leverage)
    )
    write_immutable_json(args.output, report)
    return 0


def _publication_payload(
    inputs: Mapping[str, object],
    depth: Mapping[str, object],
    equity: float,
    leverage: float,
) -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": dict(inputs),
        "candidate_depth_evidence": dict(depth),
        "depth_reference_equity_usd": equity,
        "sizing_policy": {
            "base": "fixed_percent_of_equity",
            "configured_leverage": leverage,
            "variable_tiers": "telemetry_only_not_execution_authorized",
            "readiness_is_win_probability": False,
        },
    }


def _configured_leverage(config: MultiAssetLiveConfig) -> float:
    """Return one exact configured leverage or reject a mixed policy."""
    values = {asset.leverage for asset in config.assets}
    if len(values) != 1:
        raise ValueError("candidate assets require one configured leverage")
    return values.pop()


def _input_evidence(paths: Sequence[Path]) -> dict[str, object]:
    return {str(path): {"path": str(path), **file_evidence(path)} for path in paths}


def _p99(profile: Record, side: str) -> float:
    row = _mapping(profile.get(f"{side}_visible_cost_bps"), f"{side} depth")
    value = row.get("p99")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{side} p99 depth must be numeric")
    return float(value)


def _load(path: Path, label: str) -> Record:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Return a bounded report failure without exposing live authority."""
    try:
        return run(build_parser().parse_args(argv))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"v45 growth sizing stress failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
