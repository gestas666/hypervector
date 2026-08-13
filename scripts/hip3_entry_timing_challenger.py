#!/usr/bin/env python3
"""Compare causal HIP-3 Swing entry clocks without execution authority."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.live.hip3_cohort_providers import (
    HIP3_SWING_COMMODITY_STRATEGY,
    HIP3_SWING_INDEX_STRATEGY,
)
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe
from hypervector.research.hip3_entry_timing_evaluation import (
    Hip3EntryTimingCell,
    evaluate_hip3_entry_timing,
)
from hypervector.research.hip3_entry_timing_reporting import (
    build_hip3_entry_timing_report,
    timing_trade_records,
)
from hypervector.research.hip3_lifecycle_inputs import (
    build_hip3_lifecycle_signals,
    hip3_file_reference,
    hip3_lifecycle_windows,
    load_hip3_lifecycle_assets,
    load_hip3_lifecycle_case_inputs,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_DEFAULT_CASES = {
    HIP3_SWING_INDEX_STRATEGY: Path(
        "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json"
    ),
    HIP3_SWING_COMMODITY_STRATEGY: Path(
        "data/logs/research/hip3_swing_ha_transfer_sndk_gold_disabled_brent_v1.json"
    ),
}
_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_DEFAULT_OUTPUT = Path(f"data/logs/research/hip3_entry_timing_challenger_{_STAMP}.json")
_DEFAULT_TRADES = Path(
    f"data/logs/research/hip3_entry_timing_challenger_{_STAMP}.trades.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        help="SWING_STRATEGY_ID=SOURCE_REPORT; repeat to override defaults",
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate verified open windows and publish content-addressed evidence."""
    _require_new_outputs(args.output, args.trades_output)
    cases: dict[str, object] = {}
    trade_rows: list[dict[str, object]] = []
    for strategy_id, source in _case_specs(args.case).items():
        case, rows = _run_case(strategy_id, source)
        cases[strategy_id] = case
        trade_rows.extend(rows)
    trades = _trade_frame(trade_rows)
    write_immutable_parquet(args.trades_output, trades)
    report = _top_level_report(cases, args.trades_output, len(trades))
    write_immutable_json(args.output, report)
    return report


def _run_case(
    strategy_id: str,
    source: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    inputs = load_hip3_lifecycle_case_inputs(strategy_id, source)
    recipe = configured_hip3_recipe(strategy_id)
    if not isinstance(recipe, SwingHaSignalConfig):
        raise ValueError("HIP-3 entry timing supports Swing/HA providers only")
    windows = hip3_lifecycle_windows(inputs.report)
    cells: list[Hip3EntryTimingCell] = []
    for asset, friction in load_hip3_lifecycle_assets(inputs):
        signals = build_hip3_lifecycle_signals(asset.bars, recipe)
        cells.extend(
            evaluate_hip3_entry_timing(
                asset,
                friction,
                signals,
                windows,
                provider_entry_mode=recipe.entry_mode,
            )
        )
    case = build_hip3_entry_timing_report(
        strategy_id=strategy_id,
        provider_entry_mode=recipe.entry_mode,
        cells=cells,
        windows=windows,
    )
    case["production_recipe"] = asdict(recipe)
    case["source_report"] = hip3_file_reference(source)
    case["input_evidence"] = {
        "database_path": str(inputs.database_path.resolve()),
        "source_sidecar": hip3_file_reference(inputs.sidecar_path),
        "qualification_report": hip3_file_reference(inputs.qualification_path),
    }
    return case, timing_trade_records(strategy_id, cells)


def _top_level_report(
    cases: dict[str, object],
    trade_path: Path,
    trade_count: int,
) -> dict[str, object]:
    return {
        "schema_version": "hip3_entry_timing_challenger_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "cases": cases,
        "trade_sidecar": {
            "path": str(trade_path.resolve()),
            "rows": trade_count,
            **file_evidence(trade_path),
        },
        "generator_identity": _generator_identity(),
        "decision": "diagnostic_only_pending_after_cost_manual_review",
    }


def _case_specs(values: list[str] | None) -> dict[str, Path]:
    if not values:
        return dict(_DEFAULT_CASES)
    output: dict[str, Path] = {}
    for raw in values:
        strategy, separator, path = raw.partition("=")
        if not separator or not strategy.strip() or not path.strip():
            raise ValueError("--case must use SWING_STRATEGY_ID=SOURCE_REPORT")
        if strategy in output:
            raise ValueError(f"duplicate HIP-3 timing case: {strategy}")
        recipe = configured_hip3_recipe(strategy)
        if not isinstance(recipe, SwingHaSignalConfig):
            raise ValueError("HIP-3 entry timing accepts Swing/HA providers only")
        output[strategy] = Path(path)
    return output


def _trade_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame.from_records(rows)
    return pd.DataFrame(
        {
            "strategy_id": pd.Series(dtype=str),
            "symbol": pd.Series(dtype=str),
            "phase": pd.Series(dtype=str),
            "friction": pd.Series(dtype=str),
            "timing_mode": pd.Series(dtype=str),
        }
    )


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/live/hip3_provider_recipes.py",
        root / "src/hypervector/research/hip3_entry_timing.py",
        root / "src/hypervector/research/hip3_entry_timing_evaluation.py",
        root / "src/hypervector/research/hip3_entry_timing_reporting.py",
        root / "src/hypervector/research/hip3_lifecycle_inputs.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_new_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable HIP-3 timing outputs exist: {existing}")


def main() -> int:
    """Run the challenger and print a bounded summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "cases": len(report["cases"]),
                "execution_authority": "none",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
