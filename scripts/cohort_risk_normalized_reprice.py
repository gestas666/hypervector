"""Publish exact-notional liquidity repricing for a frozen growth allocation."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import tempfile

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_recent_liquidity import (
    build_recent_liquidity_profile,
)
from hypervector.research.cohort_risk_normalized_reprice import (
    ExactVisibleCost,
    build_exact_reprice_audit,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build exact source, allocation, and per-market evidence arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--allocation", type=Path, required=True)
    parser.add_argument("--active-config", type=Path, required=True)
    parser.add_argument(
        "--hip3-profile",
        action="append",
        default=[],
        metavar="SYMBOL=PATH",
        help="exact-notional HIP-3 profile; repeat once per xyz asset",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Join exact core and HIP-3 liquidity into one repricing audit."""
    project_root = Path(__file__).resolve().parents[1]
    generator = source_tree_identity(project_root, Path(__file__).resolve())
    source = _load_json(args.source, "growth stress")
    allocation = _load_json(args.allocation, "allocation")
    exact, evidence = _collect_exact_evidence(
        source,
        allocation,
        args.active_config,
        tuple(args.hip3_profile),
    )
    report = build_exact_reprice_audit(source, allocation, exact)
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source_evidence": {
                "growth_stress": _path_evidence(args.source),
                "allocation": _path_evidence(args.allocation),
                "active_config": _path_evidence(args.active_config),
            },
            "exact_evidence": evidence,
            "generator_identity": generator,
        }
    )
    return report


def _collect_exact_evidence(
    source: Record,
    allocation: Record,
    active_config_path: Path,
    hip3_specs: Sequence[str],
) -> tuple[dict[str, ExactVisibleCost], dict[str, object]]:
    config = load_multi_asset_live_config(active_config_path, mode="observe")
    assets = {asset.symbol: asset for asset in config.assets}
    allocation_rows = _mapping(allocation.get("by_asset"), "allocation assets")
    profile_paths = _profile_paths(hip3_specs)
    if set(allocation_rows).difference(assets):
        raise ValueError("active config is missing allocation assets")
    exact: dict[str, ExactVisibleCost] = {}
    evidence: dict[str, object] = {}
    for symbol, raw in allocation_rows.items():
        asset = assets[_text(symbol, "allocation symbol")]
        row = _mapping(raw, f"allocation {symbol}")
        if asset.symbol.startswith("xyz:"):
            cost, detail = _collect_hip3(asset, row, profile_paths)
        else:
            cost, detail = _collect_core(asset, row, source)
        exact[asset.symbol] = cost
        evidence[asset.symbol] = detail
    if set(profile_paths).difference(exact):
        raise ValueError("HIP-3 profile arguments contain unused symbols")
    return exact, evidence


def _collect_core(
    asset: AssetLiveConfig, allocation: Record, source: Record
) -> tuple[ExactVisibleCost, dict[str, object]]:
    run_id = _text(source.get("evidence_run_id"), "evidence run id")
    source_assets = _mapping(
        _mapping(source.get("source_evidence"), "source evidence").get("assets"),
        "source asset evidence",
    )
    source_asset = _mapping(source_assets.get(asset.symbol), f"source {asset.symbol}")
    frozen = _mapping(source_asset.get("visible_depth"), "frozen visible depth")
    cutoff = _nonnegative_integer(
        frozen.get("window_end_timestamp_ms"), "visible window end"
    )
    with snapshot_decision_ledger(
        asset.live_ledger, run_id=run_id, allow_incomplete_tail=True
    ) as (records, ledger_evidence):
        bounded = _bounded_core_records(records, cutoff)
        baseline = _core_profile(asset, bounded, run_id, source, frozen, 750.0)
        _assert_core_baseline(asset.symbol, baseline, frozen)
        target = _positive(allocation.get("candidate_notional_usd"), "notional")
        exact = _core_profile(asset, bounded, run_id, source, frozen, target)
    return _core_exact_cost(exact, f"frozen_live_ledger:{asset.symbol}"), {
        "source": "frozen_live_ledger_window",
        "ledger": ledger_evidence,
        "baseline_reproduced": True,
        "profile": exact,
    }


def _core_profile(
    asset: AssetLiveConfig,
    records: Sequence[Record],
    run_id: str,
    source: Record,
    frozen: Record,
    notional: float,
) -> dict[str, object]:
    return build_recent_liquidity_profile(
        records,
        run_id=run_id,
        symbol=asset.symbol,
        profile_id=asset.profile_id,
        profile_fingerprint=asset.profile_fingerprint,
        notional_usd=notional,
        maximum_snapshots=_positive_integer(
            frozen.get("snapshot_count"), "frozen snapshot count"
        ),
    )


def _bounded_core_records(
    records: Sequence[Record], cutoff_ms: int
) -> tuple[Record, ...]:
    bounded: list[Record] = []
    for row in records:
        if row.get("event_type") == "configuration_identity":
            bounded.append(row)
            continue
        payload = row.get("payload")
        if row.get("event_type") != "book_observation" or not isinstance(
            payload, Mapping
        ):
            continue
        timestamp = _nonnegative_integer(payload.get("recv_ts_ms"), "book timestamp")
        if timestamp <= cutoff_ms:
            bounded.append(row)
    return tuple(bounded)


def _assert_core_baseline(symbol: str, observed: Record, frozen: Record) -> None:
    for side in ("buy", "sell"):
        observed_distribution = _mapping(
            observed.get(f"{side}_visible_cost_bps"), f"observed {side}"
        )
        frozen_distribution = _mapping(
            frozen.get(f"{side}_visible_cost_bps"), f"frozen {side}"
        )
        for quantile in ("p50", "p90", "p99"):
            left = _nonnegative(observed_distribution.get(quantile), "observed cost")
            right = _nonnegative(frozen_distribution.get(quantile), "frozen cost")
            if not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(
                    f"{symbol} exact source window does not reproduce {side} {quantile}"
                )


def _collect_hip3(
    asset: AssetLiveConfig,
    allocation: Record,
    profile_paths: Mapping[str, Path],
) -> tuple[ExactVisibleCost, dict[str, object]]:
    path = profile_paths.get(asset.symbol)
    if path is None:
        raise ValueError(f"exact HIP-3 profile is missing for {asset.symbol}")
    document = _load_json(path, f"HIP-3 profile {asset.symbol}")
    if (
        document.get("ok") is not True
        or document.get("report_only") is not True
        or document.get("execution_authority") != "none"
    ):
        raise ValueError(f"HIP-3 profile contract is invalid for {asset.symbol}")
    profile = _mapping(document.get("profile"), "HIP-3 profile")
    if profile.get("symbol") != asset.symbol:
        raise ValueError("HIP-3 profile symbol does not match active asset")
    cost = _hip3_exact_cost(profile, f"immutable_hip3_profile:{path}")
    expected = _positive(allocation.get("candidate_notional_usd"), "notional")
    if not math.isclose(cost.notional_usd, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(f"HIP-3 profile notional does not match {asset.symbol}")
    return cost, {"source": "immutable_hip3_profile", "file": _path_evidence(path)}


def _profile_paths(specs: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for spec in specs:
        symbol, separator, raw_path = spec.partition("=")
        if not separator or not symbol.strip() or not raw_path.strip():
            raise ValueError("HIP-3 profile must use SYMBOL=PATH")
        if symbol in result:
            raise ValueError(f"duplicate HIP-3 profile for {symbol}")
        result[symbol] = Path(raw_path)
    return result


def _core_exact_cost(profile: Record, evidence_source: str) -> ExactVisibleCost:
    samples = _positive_integer(profile.get("snapshot_count"), "snapshot count")
    return ExactVisibleCost(
        notional_usd=_positive(profile.get("notional_usd"), "core notional"),
        sample_count=samples,
        complete_rate=min(
            _fraction_or_zero(profile.get("buy_complete_rate"), "buy rate"),
            _fraction_or_zero(profile.get("sell_complete_rate"), "sell rate"),
        ),
        p50=_worst_side(profile, "p50"),
        p90=_worst_side(profile, "p90"),
        p99=_worst_side(profile, "p99"),
        evidence_source=evidence_source,
    )


def _hip3_exact_cost(profile: Record, evidence_source: str) -> ExactVisibleCost:
    rows = profile.get("notionals")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("exact HIP-3 profile requires one notional")
    row = _mapping(rows[0], "HIP-3 notional")
    samples = _positive_integer(row.get("samples"), "HIP-3 samples")
    return ExactVisibleCost(
        notional_usd=_positive(row.get("notional_usd"), "HIP-3 notional"),
        sample_count=samples,
        complete_rate=min(
            _fraction_or_zero(row.get("buy_complete_rate"), "buy rate"),
            _fraction_or_zero(row.get("sell_complete_rate"), "sell rate"),
        ),
        p50=_worst_side(row, "p50"),
        p90=_worst_side(row, "p90"),
        p99=_worst_side(row, "p99"),
        evidence_source=evidence_source,
    )


def _worst_side(profile: Record, quantile: str) -> float:
    return max(
        _nonnegative(
            _mapping(profile.get(f"{side}_visible_cost_bps"), side).get(quantile),
            f"{side} {quantile}",
        )
        for side in ("buy", "sell")
    )


def write_immutable_report(path: Path, report: Record) -> None:
    """Publish one new report without replacement or partial visibility."""
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
        raise FileExistsError(f"repricing output already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _fraction_or_zero(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _positive(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def main() -> int:
    """Build and publish after verifying source-tree stability."""
    args = build_parser().parse_args()
    report = run_report(args)
    generator = _mapping(report.get("generator_identity"), "generator identity")
    require_unchanged_generator(
        dict(generator),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve(),
    )
    write_immutable_report(args.out, report)
    print(json.dumps({"output": str(args.out), "execution_authority": "none"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
