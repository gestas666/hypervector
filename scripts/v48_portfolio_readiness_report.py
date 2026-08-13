#!/usr/bin/env python3
"""Build the source-backed v48 portfolio-readiness report artifact."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
import tomllib
from typing import Protocol, cast
from zoneinfo import ZoneInfo

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.growth_candidate_report_data import (
    candidate_capacity,
    candidate_routes,
    candidate_slot_risk,
)
from hypervector.research.v48_portfolio_readiness_manifest import (
    report_blocks,
    report_cards,
    report_charts,
    report_tables,
)

JsonMap = dict[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_repaired_candidate_v48"


def _load_v47_report_module() -> object:
    path = Path(__file__).with_name("v47_strategy_regression_report.py")
    spec = spec_from_file_location("v47_strategy_regression_report_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load the v47 report-builder dependency")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class V47PathSet(Protocol):
    """Minimum v47 path contract reused by this report."""

    checkpoint: Path


class V47ReportModule(Protocol):
    """Import-safe v47 report-builder interface."""

    def default_report_paths(self, root: Path) -> V47PathSet:
        """Return v47 evidence paths."""

    def build_report_artifact(self, paths: V47PathSet) -> JsonMap:
        """Build the reconciled base artifact."""


_V47 = cast(V47ReportModule, cast(object, _load_v47_report_module()))


@dataclass(frozen=True)
class ReportPaths:
    """Exact local evidence used by the v48 report."""

    base: V47PathSet
    config: Path
    stress: Path
    disposition: Path
    hip3_parity: Path

    @property
    def checkpoint(self) -> Path:
        """Return the current bounded checkpoint source."""
        return self.base.checkpoint


def default_report_paths(root: Path) -> ReportPaths:
    """Return current live and exact v48 evidence paths."""
    cohort = root / "data/logs/research/bidirectional_cohort"
    return ReportPaths(
        base=_V47.default_report_paths(root),
        config=root
        / "configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml",
        stress=cohort / "v48_growth_sizing_stress_20260812_v1.json",
        disposition=root / "docs/research-journal/v48-strategy-disposition.json",
        hip3_parity=root
        / "docs/research-journal/hip3-live-pressure-freshness-parity-v3.json",
    )


def build_report_artifact(paths: ReportPaths) -> JsonMap:
    """Build one reconciled portable v48 report artifact."""
    base = _V47.build_report_artifact(paths.base)
    config = _load_toml(paths.config)
    stress = _load_json(paths.stress)
    disposition = _load_json(paths.disposition)
    hip3_parity = _load_json(paths.hip3_parity)
    _validate_v48(config, stress, disposition, hip3_parity)
    datasets = _datasets(base, config, stress, disposition, hip3_parity)
    sources = _sources(base, paths)
    generated = datetime.now(tz=UTC).isoformat()
    cutoff = str(_load_json(paths.checkpoint)["generated_at_utc"])
    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Hypervector $5K Growth Readiness",
        "description": (
            "Source-backed strategy diagnosis, regime evidence, live boundary, "
            "and exact v48 growth sizing."
        ),
        "generatedAt": generated,
        "cards": report_cards(),
        "charts": report_charts(),
        "tables": report_tables(),
        "blocks": report_blocks(_cutoff_label(cutoff)),
        "sources": sources,
    }
    return {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated,
            "status": "ready",
            "datasets": datasets,
        },
        "sources": sources,
    }


def _validate_v48(
    config: JsonMap,
    stress: JsonMap,
    disposition: JsonMap,
    hip3_parity: JsonMap,
) -> None:
    assets = [_mapping(raw, "asset") for raw in _sequence(config["assets"], "assets")]
    providers = [
        _mapping(raw, "provider") for raw in _sequence(config["providers"], "providers")
    ]
    routes = sum(
        len(cast(list[str], provider["execution_symbols"])) for provider in providers
    )
    directions = sum(
        len(cast(list[str], provider["execution_symbols"]))
        * len(cast(list[str], provider["sides"]))
        for provider in providers
    )
    defect = _defect_summary(hip3_parity)
    exact = (
        config["profile"] == _PROFILE_ID
        and stress["profile_id"] == _PROFILE_ID
        and disposition["profile_id"] == _PROFILE_ID
        and stress["profile_fingerprint"] == disposition["profile_fingerprint"]
        and {str(asset["symbol"]) for asset in assets} == {"BTC", "ETH", "SOL", "HYPE"}
        and all(float(asset["leverage"]) == 10.0 for asset in assets)
        and sum(float(asset["margin_fraction"]) for asset in assets) == 0.6
        and len(providers) == 4
        and routes == 5
        and directions == 8
        and defect["affected_closed_trades"] == 5
        and defect["affected_net_pnl_usd"] == -2.713721
    )
    if not exact:
        raise ValueError("v48 report evidence does not match the exact candidate")


def _datasets(
    base: JsonMap,
    config: JsonMap,
    stress: JsonMap,
    disposition: JsonMap,
    hip3_parity: JsonMap,
) -> JsonMap:
    datasets = dict(
        _mapping(_mapping(base["snapshot"], "snapshot")["datasets"], "datasets")
    )
    datasets["strategy_decisions"] = [
        _mapping(row, "decision")
        for row in _sequence(disposition["decisions"], "decisions")
    ]
    datasets["candidate_routes"] = candidate_routes(config, stress, _strategy_label)
    datasets["candidate_capacity"] = [candidate_capacity(config, stress, "v48")]
    datasets["candidate_slot_risk"] = candidate_slot_risk(stress)
    datasets["defect_summary"] = [_defect_summary(hip3_parity)]
    datasets["regime_cluster_accuracy"] = [
        row
        for row in cast(list[JsonMap], datasets["regime_accuracy"])
        if row["series"] in {"up clusters", "down clusters"}
    ]
    return datasets


def _sources(base: JsonMap, paths: ReportPaths) -> list[JsonMap]:
    manifest = _mapping(base["manifest"], "manifest")
    inherited = [
        _mapping(source, "source")
        for source in _sequence(manifest["sources"], "sources")
        if _mapping(source, "source")["id"]
        not in {"v47-config", "v47-stress", "hip3-parity", "strategy-disposition"}
    ]
    return [
        *inherited,
        _source("v48-config", "v48 exact configuration", paths.config),
        _source("v48-stress", "v48 route-aware friction stress", paths.stress),
        _source(
            "hip3-parity",
            "latest HIP3 live/research freshness parity",
            paths.hip3_parity,
        ),
        _source(
            "strategy-disposition",
            "v48 defect-versus-edge disposition",
            paths.disposition,
        ),
    ]


def _defect_summary(parity: JsonMap) -> JsonMap:
    attribution = _mapping(parity["closed_pnl_attribution"], "attribution")
    return {
        "affected_closed_trades": attribution["affected_hip3_closed_trades"],
        "affected_net_pnl_usd": attribution["affected_hip3_net_pnl_usd"],
        "affected_loss_fraction": float(
            attribution["affected_share_of_absolute_run_loss_pct"]
        )
        / 100.0,
    }


def _source(key: str, label: str, path: Path) -> JsonMap:
    portable = path.relative_to(Path.cwd())
    query_path = str(portable).replace("'", "''")
    reader = "read_text" if path.suffix == ".toml" else "read_json_auto"
    return {
        "id": key,
        "label": label,
        "path": str(portable),
        "query": {
            "engine": "duckdb",
            "sql": f"SELECT * FROM {reader}('{query_path}')",
            "description": f"Loads {label}.",
        },
    }


def _strategy_label(strategy: str) -> str:
    labels = {
        "hulk_expansion_short_robust_v3": "BTC Hulk Short v3",
        "liquidity_sweep_long_1h_stop60_target60_v2": "BTC Sweep Long",
        "range_onset_bidirectional_v1": "Range Onset",
        "hype_breakout_compression_pullback_bidirectional_v1": "HYPE Compression",
    }
    return labels.get(strategy, strategy)


def _cutoff_label(value: str) -> str:
    observed = datetime.fromisoformat(value).astimezone(ZoneInfo("America/New_York"))
    return observed.strftime("%B %d, %Y at %I:%M:%S %p EDT").replace(" 0", " ")


def _load_json(path: Path) -> JsonMap:
    if not path.is_file():
        raise FileNotFoundError(f"report evidence does not exist: {path}")
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _load_toml(path: Path) -> JsonMap:
    if not path.is_file():
        raise FileNotFoundError(f"report evidence does not exist: {path}")
    return _mapping(tomllib.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> JsonMap:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(JsonMap, value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only artifact command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    """Publish one immutable report artifact and print its path."""
    args = build_parser().parse_args()
    artifact = build_report_artifact(default_report_paths(args.root.resolve()))
    write_immutable_json(args.output, artifact)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
