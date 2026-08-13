#!/usr/bin/env python3
"""Run the frozen all-asset 15m Swing/HA/order-block experiment."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.low_tf_multi_asset_contract import default_low_tf_contract
from hypervector.research.swing_ha_experiment import (
    SwingHaEvaluation,
    evaluate_development_grid,
    evaluate_frozen_segment,
    evaluation_summaries,
    gap_touched_trade_count,
    selected_from_evaluations,
)
from hypervector.research.swing_ha_experiment_data import (
    SwingHaAssetData,
    default_asset_inputs,
    load_asset_data,
)
from hypervector.research.swing_ha_screen import (
    SwingHaScreenCell,
    base_trial_grid,
    order_block_trial_grid,
    signal_config_id,
    stress_screen_config,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_SCHEMA = "swing_ha_order_block_15m_v1"


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only experiment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/swing_ha_order_block_15m_all_assets_v1.json"),
    )
    parser.add_argument(
        "--trades-output",
        type=Path,
        default=Path(
            "data/logs/research/swing_ha_order_block_15m_all_assets_v1.trades.parquet"
        ),
    )
    return parser


def run_experiment(
    assets: tuple[SwingHaAssetData, ...],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Tune on development and evaluate one frozen config out of sample."""
    contract = default_low_tf_contract()
    development = contract.segment("development")
    validation = contract.segment("validation")
    pseudo_holdout = contract.segment("pseudo_holdout")
    base_evaluations = evaluate_development_grid(
        assets, base_trial_grid(), start=development[0], end=development[1]
    )
    selected_base = selected_from_evaluations(base_evaluations)
    block_evaluations = evaluate_development_grid(
        assets,
        order_block_trial_grid(selected_base),
        start=development[0],
        end=development[1],
    )
    selected = selected_from_evaluations(block_evaluations)
    scenarios, trades = _out_of_sample_scenarios(
        assets, selected, validation, pseudo_holdout
    )
    report = _report(
        assets,
        development,
        validation,
        pseudo_holdout,
        base_evaluations,
        selected_base,
        block_evaluations,
        selected,
        scenarios,
    )
    return report, trades


def _out_of_sample_scenarios(
    assets: tuple[SwingHaAssetData, ...],
    config: SwingHaSignalConfig,
    validation: tuple[pd.Timestamp, pd.Timestamp],
    pseudo_holdout: tuple[pd.Timestamp, pd.Timestamp],
) -> tuple[dict[str, object], pd.DataFrame]:
    scenario_reports: dict[str, object] = {}
    trade_frames: list[pd.DataFrame] = []
    for segment, window in (
        ("validation", validation),
        ("pseudo_holdout", pseudo_holdout),
    ):
        for scenario, screen, delay in (
            ("nominal", None, 0),
            ("cost_stress_20bps", stress_screen_config(), 0),
            ("entry_delay_1bar", None, 1),
        ):
            cells = evaluate_frozen_segment(
                assets,
                config,
                start=window[0],
                end=window[1],
                screen_config=screen,
                entry_delay_bars=delay,
            )
            key = f"{segment}:{scenario}"
            scenario_reports[key] = _scenario_report(assets, cells, window)
            trade_frames.extend(_trade_frames(cells, segment, scenario, config))
    if not trade_frames:
        return scenario_reports, pd.DataFrame()
    return scenario_reports, pd.concat(trade_frames, ignore_index=True)


def _scenario_report(
    assets: tuple[SwingHaAssetData, ...],
    cells: tuple[SwingHaScreenCell, ...],
    window: tuple[pd.Timestamp, pd.Timestamp],
) -> dict[str, object]:
    asset_lookup = {asset.symbol: asset for asset in assets}
    compact: list[dict[str, object]] = []
    for cell in cells:
        values = asdict(cell)
        values.pop("trade_records")
        bars = _window_bars(asset_lookup[cell.symbol].bars, window)
        values["gap_touched_trades"] = gap_touched_trade_count(bars, cell)
        compact.append(values)
    return {
        "start_utc": window[0].isoformat(),
        "end_utc": window[1].isoformat(),
        "asset_cells": compact,
        "total_net_pnl_usd_independent_accounts": sum(
            cell.net_pnl_usd for cell in cells
        ),
        "positive_assets": sum(cell.net_pnl_usd > 0.0 for cell in cells),
        "total_trades": sum(cell.completed_trades for cell in cells),
        "long_trades": sum(cell.direction_trades["long"] for cell in cells),
        "short_trades": sum(cell.direction_trades["short"] for cell in cells),
        "liquidations": sum(cell.liquidations for cell in cells),
        "execution_authority": "none",
    }


def _trade_frames(
    cells: tuple[SwingHaScreenCell, ...],
    segment: str,
    scenario: str,
    config: SwingHaSignalConfig,
) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for cell in cells:
        frame = pd.DataFrame(cell.trade_records)
        if frame.empty:
            continue
        frame.insert(0, "config_id", signal_config_id(config))
        frame.insert(0, "scenario", scenario)
        frame.insert(0, "segment", segment)
        frame.insert(0, "symbol", cell.symbol)
        frame["execution_authority"] = "none"
        frames.append(frame)
    return frames


def _report(
    assets: tuple[SwingHaAssetData, ...],
    development: tuple[pd.Timestamp, pd.Timestamp],
    validation: tuple[pd.Timestamp, pd.Timestamp],
    pseudo_holdout: tuple[pd.Timestamp, pd.Timestamp],
    base: tuple[SwingHaEvaluation, ...],
    selected_base: SwingHaSignalConfig,
    blocks: tuple[SwingHaEvaluation, ...],
    selected: SwingHaSignalConfig,
    scenarios: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "place_attempted": False,
        "windows": {
            "development": _window_dict(development),
            "validation": _window_dict(validation),
            "pseudo_holdout": _window_dict(pseudo_holdout),
        },
        "source_identity": [asset.source_identity for asset in assets],
        "generator_identity": _generator_identity(),
        "execution_assumptions": _execution_assumptions(),
        "selection_rule": (
            "lexicographic bidirectional assets, positive assets/folds, median and "
            "worst fold return, median coin return, fewer liquidations/drawdown"
        ),
        "base_trial_count": len(base),
        "base_trials": evaluation_summaries(base),
        "selected_base_config": asdict(selected_base),
        "order_block_trial_count": len(blocks),
        "order_block_trials": evaluation_summaries(blocks),
        "selected_frozen_config": asdict(selected),
        "out_of_sample_scenarios": scenarios,
        "promotion": None,
        "limitations": _limitations(),
    }


def _execution_assumptions() -> dict[str, object]:
    return {
        "initial_equity_per_independent_asset_usd": 15_000.0,
        "margin_fraction": 0.10,
        "leverage": 5.0,
        "nominal_fee_bps_per_market_side": 4.5,
        "nominal_slippage_bps_per_market_side": 2.0,
        "nominal_round_trip_bps": 13.0,
        "stress_round_trip_bps": 20.0,
        "funding": "authentic_hourly_hyperliquid",
        "liquidation": "isolated_margin_conservative_native_bar",
    }


def _limitations() -> list[str]:
    return [
        "validation and pseudo-holdout periods were exposed by prior project research",
        "independent asset screens are not a shared-account portfolio forecast",
        "native 15m bars use liquidation-first ordering for ambiguous stop bars",
        "market impact and private order acknowledgement latency are not simulated",
        "continuity-filled source intervals remain explicit and trade-attributed",
    ]


def _window_bars(
    bars: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]
) -> pd.DataFrame:
    return bars.loc[
        bars.index.to_series().ge(window[0]) & bars.index.to_series().lt(window[1])
    ]


def _window_dict(window: tuple[pd.Timestamp, pd.Timestamp]) -> dict[str, str]:
    return {"start_utc": window[0].isoformat(), "end_utc": window[1].isoformat()}


def _generator_identity() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/swing_ha_signals.py",
        root / "src/hypervector/research/swing_order_blocks.py",
        root / "src/hypervector/research/swing_ha_screen.py",
        root / "src/hypervector/research/swing_ha_experiment.py",
        root / "src/hypervector/research/swing_ha_experiment_data.py",
    )
    return {str(path.relative_to(root)): _file_sha256(path) for path in paths}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """Run once and publish immutable JSON plus selected-trade evidence."""
    args = build_parser().parse_args()
    if args.output.exists() or args.trades_output.exists():
        raise FileExistsError("Swing/HA immutable output already exists")
    assets = tuple(
        load_asset_data(item) for item in default_asset_inputs(args.data_root)
    )
    report, trades = run_experiment(assets)
    write_immutable_parquet(args.trades_output, trades)
    report["trade_sidecar"] = {
        "path": str(args.trades_output.resolve()),
        "rows": len(trades),
        **file_evidence(args.trades_output),
    }
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
