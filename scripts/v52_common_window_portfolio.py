#!/usr/bin/env python3
"""Publish the exact opened-window v52 shared-account replay."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import cast

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.hype_breakout_exit_models import (
    HypeExitReason,
    HypeExitTrade,
    HypeSide,
)
from hypervector.research.v52_common_window_portfolio import (
    HULK_ROUTE,
    HYPE_ROUTE,
    SWEEP_ROUTE,
    build_v52_common_window_portfolio,
)

_PROFILE = Path(
    "configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml"
)
_HULK = Path(
    "data/logs/research/20260811_hulk_short_robust_v3_btc_forward_nominal.json"
)
_SWEEP = Path(
    "data/logs/research/bidirectional_cohort/"
    "btc_liquidity_sweep_taker_parity_20260811_v2.json"
)
_HYPE_REPORT = Path(
    "data/logs/research/"
    "hype_compression_breakout_challenger_20260816_v6_alignment/report.json"
)
_IMPLEMENTATION = (
    Path(__file__),
    Path("src/hypervector/research/v52_common_window_portfolio.py"),
    Path("src/hypervector/research/current_cohort_shared_portfolio.py"),
    Path("src/hypervector/research/evidence_selected_portfolio.py"),
    Path("src/hypervector/research/lean_successor_portfolio.py"),
    Path("src/hypervector/research/shared_trade_portfolio.py"),
    Path("src/hypervector/research/hype_breakout_exit_models.py"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_PROFILE)
    parser.add_argument("--hulk", type=Path, default=_HULK)
    parser.add_argument("--sweep", type=Path, default=_SWEEP)
    parser.add_argument("--hype-report", type=Path, default=_HYPE_REPORT)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact immutable inputs and construct one v52 portfolio report."""
    hype_report = _load_json(args.hype_report)
    sidecar = _sidecar_path(args.hype_report, hype_report)
    data_paths = (args.config, args.hulk, args.sweep, args.hype_report, sidecar)
    before_data = _evidence(data_paths)
    before_code = _evidence(_IMPLEMENTATION)
    config = load_multi_asset_live_config(args.config, mode="observe")
    _validate_profile(config)
    artifact = build_v52_common_window_portfolio(
        _load_json(args.hulk),
        _load_json(args.sweep),
        _aligned_hype_trades(sidecar),
    )
    _require_evidence_unchanged(before_data, data_paths)
    _require_evidence_unchanged(before_code, _IMPLEMENTATION)
    artifact.update(_report_metadata(config, hype_report, before_data, before_code))
    return artifact


def publish(path: Path, report: Mapping[str, object]) -> None:
    """Publish one append-only JSON artifact without overwrite authority."""
    write_immutable_json(path, dict(report))


def _validate_profile(config: object) -> None:
    profile_id = getattr(config, "profile_id", None)
    symbols = getattr(config, "symbols", None)
    maximum_positions = getattr(config, "maximum_positions", None)
    providers = getattr(config, "providers", ())
    actual = {
        (provider.strategy_id, symbol): provider.priority
        for provider in providers
        for symbol in provider.execution_symbols
    }
    expected = {HULK_ROUTE: 20, SWEEP_ROUTE: 10, HYPE_ROUTE: 45}
    if profile_id != "multi_asset_growth_first_5000_evidence_bound_successor_v52":
        raise ValueError("common-window replay requires the exact v52 profile")
    if symbols != ("BTC", "HYPE") or maximum_positions != 10:
        raise ValueError("v52 profile assets or account capacity changed")
    if actual != expected:
        raise ValueError("v52 provider routes or priorities changed")


def _aligned_hype_trades(path: Path) -> tuple[HypeExitTrade, ...]:
    frame = pd.read_parquet(path)
    required = {"cohort", "censored", *HypeExitTrade.__dataclass_fields__}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"HYPE alignment sidecar missing columns: {sorted(missing)}")
    selected = frame.loc[(frame["cohort"] == "aligned_only") & ~frame["censored"]]
    if selected.empty:
        raise ValueError("HYPE alignment sidecar has no resolved aligned-only trades")
    return tuple(_hype_trade(row) for row in selected.to_dict("records"))


def _hype_trade(row: Mapping[str, object]) -> HypeExitTrade:
    return HypeExitTrade(
        side=cast(HypeSide, _text(row, "side")),
        signal_time_utc=_text(row, "signal_time_utc"),
        entry_time_utc=_text(row, "entry_time_utc"),
        exit_time_utc=_text(row, "exit_time_utc"),
        entry_price=_number(row, "entry_price"),
        exit_price=_number(row, "exit_price"),
        stop_price=_number(row, "stop_price"),
        gross_return_bps=_number(row, "gross_return_bps"),
        fee_bps=_number(row, "fee_bps"),
        funding_bps=_number(row, "funding_bps"),
        net_return_bps=_number(row, "net_return_bps"),
        hold_minutes=_integer(row, "hold_minutes"),
        maximum_favorable_excursion_bps=_number(row, "maximum_favorable_excursion_bps"),
        maximum_adverse_excursion_bps=_number(row, "maximum_adverse_excursion_bps"),
        exit_reason=cast(HypeExitReason, _text(row, "exit_reason")),
    )


def _sidecar_path(report_path: Path, report: Mapping[str, object]) -> Path:
    sidecars = _mapping(report, "sidecars")
    manifest = _mapping(sidecars, "alignment_confirmation_trades")
    recorded = Path(_text(manifest, "path"))
    published = report_path.parent / recorded.name
    evidence = file_evidence(published)
    if evidence["sha256"] != _text(manifest, "sha256"):
        raise ValueError("HYPE alignment sidecar checksum differs from report")
    if evidence["bytes"] != _integer(manifest, "bytes"):
        raise ValueError("HYPE alignment sidecar bytes differ from report")
    return published


def _report_metadata(
    config: object,
    hype_report: Mapping[str, object],
    data: list[dict[str, object]],
    code: list[dict[str, object]],
) -> dict[str, object]:
    alignment = _mapping(hype_report, "compression_alignment_replay")
    return {
        "hypothesis_id": "v52-common-window-portfolio-interaction",
        "profile": {
            "profile_id": getattr(config, "profile_id"),
            "profile_fingerprint": getattr(config, "profile_fingerprint"),
            "configured_assets": list(getattr(config, "symbols")),
        },
        "sidecar_contract": {
            "cohort": "aligned_only",
            "selection_performed": alignment.get("selection_performed"),
        },
        "data_evidence": data,
        "implementation_evidence": code,
        "decision": "collect_forward_v52_no_live_change_from_this_report",
        "confidence": "low_economic_high_calculation",
        "explicit_approval_requested": False,
        "falsifier": (
            "A common-window rerun with exact v52 live lifecycles, costs, and both "
            "HYPE sides can materially reverse this sparse descriptive result."
        ),
    }


def _evidence(paths: tuple[Path, ...]) -> list[dict[str, object]]:
    return [{"path": str(path), **file_evidence(path)} for path in paths]


def _require_evidence_unchanged(
    expected: list[dict[str, object]], paths: tuple[Path, ...]
) -> None:
    if expected != _evidence(paths):
        raise RuntimeError("v52 common-window evidence changed during evaluation")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"v52 evidence must be a JSON object: {path}")
    return value


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"v52 evidence {key} must be an object")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"v52 evidence {key} must be non-empty text")
    return value


def _number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"v52 evidence {key} must be numeric")
    return float(value)


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"v52 evidence {key} must be an integer")
    return value


def main() -> int:
    """Run the exact report-only replay and publish one immutable result."""
    args = build_parser().parse_args()
    report = run(args)
    publish(args.out, report)
    full = report["windows"]["opened_common"]["nominal"]["v52_full"]
    print(
        json.dumps(
            {
                "status": "published_report_only",
                "output": str(args.out),
                "completed_trades": full["completed_trades"],
                "net_pnl_usd": full["net_pnl_usd"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
