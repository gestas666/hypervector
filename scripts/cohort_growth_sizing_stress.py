"""Publish immutable report-only $5k cohort sizing and loss stress evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
import json
from math import isfinite
import os
from pathlib import Path
import tempfile

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.cohort_monitor_identity import active_ledger_identity
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_growth_sizing_evidence import (
    hip3_visible_quantiles,
    latest_funding_rate,
    resolve_one_way_taker_fee_bps,
    visible_quantiles,
)
from hypervector.research.cohort_growth_sizing_stress import (
    AssetGrowthStressInput,
    VisibleCostQuantiles,
    build_growth_sizing_stress,
)
from hypervector.research.cohort_recent_liquidity import (
    build_recent_liquidity_profile,
)
from hypervector.research.live_ledger_snapshot import (
    snapshot_compatible_execution_ledger,
    snapshot_decision_ledger,
)
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

Record = Mapping[str, object]
FundingMethod = Callable[[str, int, int], object]

_DEFAULT_CONFIG = Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml")
_DEFAULT_EQUITY_USD = 5_000.0
_DEFAULT_MAXIMUM_SNAPSHOTS = 240
_HIP3_ROSTER_PATH = Path("data/runtime/research/hip3_roster_latest.json")
_HIP3_PROFILE_PATHS = {
    "xyz:BRENTOIL": Path(
        "data/logs/research/"
        "xyz_brentoil_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:GOLD": Path(
        "data/logs/research/"
        "xyz_gold_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:SNDK": Path(
        "data/logs/research/"
        "xyz_sndk_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:SP500": Path(
        "data/logs/research/"
        "xyz_sp500_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
    "xyz:SPCX": Path(
        "data/logs/research/"
        "xyz_spcx_liquidity_profile_notional750_1250_1750_20260810.json"
    ),
}


def build_parser() -> argparse.ArgumentParser:
    """Build explicit report-only growth stress arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument(
        "--active-config",
        type=Path,
        help="active profile supplying exact live evidence for the candidate",
    )
    parser.add_argument("--equity-usd", type=float, default=_DEFAULT_EQUITY_USD)
    parser.add_argument(
        "--margin-fraction",
        type=float,
        help="report-only candidate margin fraction per occupied slot",
    )
    parser.add_argument(
        "--maximum-snapshots", type=int, default=_DEFAULT_MAXIMUM_SNAPSHOTS
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def candidate_margin_fraction(current: float, requested: float | None) -> float:
    """Select an explicit research-only margin fraction without mutating config."""
    value = current if requested is None else requested
    fraction = _positive(value, "candidate margin fraction")
    if fraction > 1.0:
        raise ValueError("candidate margin fraction must not exceed one")
    return fraction


def candidate_evidence_asset_pairs(
    candidate_config: MultiAssetLiveConfig,
    evidence_config: MultiAssetLiveConfig,
) -> tuple[tuple[AssetLiveConfig, AssetLiveConfig], ...]:
    """Pair every candidate asset with exact-symbol active evidence."""
    if candidate_config.network != evidence_config.network:
        raise ValueError("candidate and active evidence networks do not match")
    if candidate_config.margin_mode != evidence_config.margin_mode:
        raise ValueError("candidate and active evidence margin modes do not match")
    evidence_by_symbol = {asset.symbol: asset for asset in evidence_config.assets}
    missing = tuple(
        asset.symbol
        for asset in candidate_config.assets
        if asset.symbol not in evidence_by_symbol
    )
    if missing:
        raise ValueError(
            "active evidence config is missing candidate symbols: " + ", ".join(missing)
        )
    return tuple(
        (asset, evidence_by_symbol[asset.symbol]) for asset in candidate_config.assets
    )


def write_immutable_report(path: Path, report: Mapping[str, object]) -> None:
    """Write one new report without replacing prior evidence."""
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise FileExistsError(
            f"growth sizing stress output already exists: {path}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Collect bound live/archive evidence and build one report."""
    project_root = Path(__file__).resolve().parents[1]
    generator = source_tree_identity(project_root, Path(__file__).resolve())
    candidate_config = load_multi_asset_live_config(args.config, mode="observe")
    evidence_config_path = args.active_config or args.config
    evidence_config = load_multi_asset_live_config(
        evidence_config_path,
        mode="observe",
    )
    identity = active_ledger_identity(evidence_config)
    hip3_roster = _load_json(_HIP3_ROSTER_PATH, "HIP-3 roster")
    configured_margin_fraction = _uniform_asset_value(
        candidate_config,
        "margin_fraction",
    )
    margin_fraction = candidate_margin_fraction(
        configured_margin_fraction,
        args.margin_fraction,
    )
    leverage = _uniform_asset_value(candidate_config, "leverage")
    notional = _positive(args.equity_usd, "equity_usd") * margin_fraction * leverage
    funding, funding_evidence = _official_funding(candidate_config.symbols)
    inputs, evidence = _asset_inputs(
        candidate_config,
        evidence_config,
        identity.run_id,
        notional,
        _positive_integer(args.maximum_snapshots, "maximum_snapshots"),
        funding,
        hip3_roster,
    )
    report = build_growth_sizing_stress(
        equity_usd=args.equity_usd,
        margin_fraction=margin_fraction,
        leverage=leverage,
        maximum_positions=candidate_config.maximum_positions,
        assets=inputs,
    )
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "profile_id": candidate_config.profile_id,
            "profile_fingerprint": candidate_config.profile_fingerprint,
            "evidence_run_id": identity.run_id,
            "evidence_profile_id": evidence_config.profile_id,
            "evidence_profile_fingerprint": evidence_config.profile_fingerprint,
            "generator_identity": generator,
            "sizing_source": {
                "configured_margin_fraction": configured_margin_fraction,
                "candidate_margin_fraction": margin_fraction,
                "candidate_override": args.margin_fraction is not None,
            },
            "source_evidence": {
                "config": _path_evidence(args.config),
                "active_config": _path_evidence(evidence_config_path),
                "hip3_roster": _path_evidence(_HIP3_ROSTER_PATH),
                "assets": evidence,
                "official_funding": funding_evidence,
            },
        }
    )
    return report


def _asset_inputs(
    candidate_config: MultiAssetLiveConfig,
    evidence_config: MultiAssetLiveConfig,
    run_id: str,
    notional_usd: float,
    maximum_snapshots: int,
    funding: Mapping[str, float],
    hip3_roster: Record,
) -> tuple[tuple[AssetGrowthStressInput, ...], dict[str, object]]:
    inputs: list[AssetGrowthStressInput] = []
    evidence: dict[str, object] = {}
    for candidate_asset, evidence_asset in candidate_evidence_asset_pairs(
        candidate_config,
        evidence_config,
    ):
        with snapshot_decision_ledger(
            evidence_asset.live_ledger,
            run_id=run_id,
            allow_incomplete_tail=True,
        ) as (records, ledger_evidence):
            visible, visible_evidence = _asset_visible_evidence(
                evidence_asset,
                records,
                run_id,
                notional_usd,
                maximum_snapshots,
            )
            with snapshot_compatible_execution_ledger(
                evidence_asset.live_ledger,
                run_id=run_id,
                allow_incomplete_tail=True,
            ) as (compatible, compatible_evidence):
                fee, fee_evidence = resolve_one_way_taker_fee_bps(
                    compatible,
                    symbol=evidence_asset.symbol,
                    profile_id=evidence_asset.profile_id,
                    profile_fingerprint=evidence_asset.profile_fingerprint,
                    hip3_roster=hip3_roster
                    if evidence_asset.symbol.startswith("xyz:")
                    else None,
                )
                inputs.append(
                    AssetGrowthStressInput(
                        symbol=candidate_asset.symbol,
                        stop_bps=candidate_asset.stop_bps,
                        one_way_taker_fee_bps=fee,
                        visible_cost=visible,
                        latest_hourly_funding_rate=funding[candidate_asset.symbol],
                        current_profile_cap_usd=candidate_asset.max_notional_usd,
                    )
                )
                evidence[candidate_asset.symbol] = {
                    "candidate_profile_id": candidate_asset.profile_id,
                    "candidate_profile_fingerprint": (
                        candidate_asset.profile_fingerprint
                    ),
                    "evidence_profile_id": evidence_asset.profile_id,
                    "evidence_profile_fingerprint": (
                        evidence_asset.profile_fingerprint
                    ),
                    "ledger": ledger_evidence,
                    "compatible_execution_ledger": compatible_evidence,
                    "fee": fee_evidence,
                    "visible_depth": visible_evidence,
                }
    return tuple(inputs), evidence


def _asset_visible_evidence(
    asset: AssetLiveConfig,
    records: Sequence[Record],
    run_id: str,
    notional_usd: float,
    maximum_snapshots: int,
) -> tuple[VisibleCostQuantiles, Record]:
    hip3_path = _HIP3_PROFILE_PATHS.get(asset.symbol)
    if hip3_path is not None:
        document = _load_json(hip3_path, "HIP-3 liquidity report")
        profile = _mapping(document.get("profile"), "HIP-3 liquidity profile")
        if profile.get("symbol") != asset.symbol:
            raise ValueError("HIP-3 liquidity symbol does not match asset")
        return hip3_visible_quantiles(document, notional_usd=notional_usd), {
            "source": "historical_0xarchive",
            "file": _path_evidence(hip3_path),
        }
    recent = build_recent_liquidity_profile(
        records,
        run_id=run_id,
        symbol=asset.symbol,
        profile_id=asset.profile_id,
        profile_fingerprint=asset.profile_fingerprint,
        notional_usd=notional_usd,
        maximum_snapshots=maximum_snapshots,
    )
    return visible_quantiles(recent), recent


def _official_funding(
    symbols: Sequence[str],
) -> tuple[dict[str, float], dict[str, object]]:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    end = datetime.now(UTC)
    start = end - timedelta(hours=3)
    bounds = (int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    core = Info(
        base_url=constants.MAINNET_API_URL,
        skip_ws=True,
        timeout=10.0,
    )
    xyz = Info(
        base_url=constants.MAINNET_API_URL,
        skip_ws=True,
        perp_dexs=["xyz"],
        timeout=10.0,
    )
    rates: dict[str, float] = {}
    raw: dict[str, object] = {}
    for symbol in symbols:
        client = xyz if symbol.startswith("xyz:") else core
        method = _funding_method(client)
        rows = _funding_rows(method(symbol, bounds[0], bounds[1]), symbol)
        rates[symbol] = latest_funding_rate(
            rows, symbol=symbol, start_ms=bounds[0], end_ms=bounds[1]
        )
        raw[symbol] = rows
    return rates, {
        "source": "official_hyperliquid_fundingHistory",
        "requested_start_ms": bounds[0],
        "requested_end_ms": bounds[1],
        "rows_by_symbol": raw,
    }


def _funding_method(client: object) -> FundingMethod:
    method = getattr(client, "funding_history", None)
    if not callable(method):
        raise RuntimeError("official Hyperliquid client lacks funding_history")
    return method


def _funding_rows(value: object, symbol: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"official funding history is empty for {symbol}")
    return tuple(_mapping(row, "official funding row") for row in value)


def _uniform_asset_value(config: MultiAssetLiveConfig, field: str) -> float:
    values = {
        _positive(getattr(asset, field), f"asset {field}") for asset in config.assets
    }
    if len(values) != 1:
        raise ValueError(f"growth sizing requires one common asset {field}")
    return values.pop()


def _load_json(path: Path, label: str) -> Record:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}: {exc}") from exc
    return _mapping(value, label)


def _path_evidence(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    evidence["path"] = str(path)
    return evidence


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def main() -> int:
    """Build and publish one immutable report without execution authority."""
    args = build_parser().parse_args()
    report = run_report(args)
    generator = dict(_mapping(report.get("generator_identity"), "generator identity"))
    require_unchanged_generator(
        generator,
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve(),
    )
    write_immutable_report(args.out, report)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "profile_id": report["profile_id"],
                "run_id": report["evidence_run_id"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
