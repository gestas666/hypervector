#!/usr/bin/env python3
"""Publish a bounded, non-executable v25 HIP-3 lifecycle bar diagnostic."""

from __future__ import annotations

import argparse
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
    HIP3_BREAKOUT_COMMODITY_STRATEGY,
    HIP3_BREAKOUT_INDEX_STRATEGY,
    HIP3_SWING_COMMODITY_STRATEGY,
    HIP3_SWING_INDEX_STRATEGY,
)
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe
from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleCell,
    Hip3DeployedLifecycleSpec,
    evaluate_deployed_lifecycle,
)
from hypervector.research.hip3_deployed_lifecycle_reporting import (
    deployed_lifecycle_case_report,
    lifecycle_trade_records,
)
from hypervector.research.hip3_lifecycle_inputs import (
    Hip3LifecycleCaseInputs,
    build_hip3_lifecycle_signals,
    hip3_file_reference,
    hip3_lifecycle_windows,
    load_hip3_lifecycle_assets,
    load_hip3_lifecycle_case_inputs,
)

_DEFAULT_CASES = {
    HIP3_SWING_INDEX_STRATEGY: Path(
        "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json"
    ),
    HIP3_BREAKOUT_INDEX_STRATEGY: Path(
        "data/logs/research/hip3_breakout_pressure_transfer_sp500_spcx_v1.json"
    ),
    HIP3_SWING_COMMODITY_STRATEGY: Path(
        "data/logs/research/hip3_swing_ha_transfer_sndk_gold_disabled_brent_v1.json"
    ),
    HIP3_BREAKOUT_COMMODITY_STRATEGY: Path(
        "data/logs/research/hip3_breakout_pressure_transfer_sndk_gold_disabled_brent_v1.json"
    ),
}
_DEFAULT_OUTPUT = Path(
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.json"
)
_DEFAULT_TRADES = Path(
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.trades.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        help="STRATEGY_ID=SOURCE_REPORT; repeat to override the four defaults",
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    parser.add_argument(
        "--signal-exit-policy",
        choices=("ignore", "honor", "early_adverse"),
        default="ignore",
    )
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate open windows and atomically publish immutable evidence."""
    _require_new_outputs(args.output, args.trades_output)
    specs = _case_specs(args.case)
    lifecycle = Hip3DeployedLifecycleSpec(
        signal_exit_policy=args.signal_exit_policy,
    )
    cases: dict[str, object] = {}
    trade_rows: list[dict[str, object]] = []
    for strategy_id, report_path in specs.items():
        inputs = load_hip3_lifecycle_case_inputs(strategy_id, report_path)
        case, rows = _run_case(inputs, lifecycle)
        cases[strategy_id] = case
        trade_rows.extend(rows)
    trades = _trade_frame(trade_rows)
    write_immutable_parquet(args.trades_output, trades)
    report = {
        "schema_version": "hip3_v25_lifecycle_bar_diagnostic_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "cases": cases,
        "trade_sidecar": {
            "path": str(args.trades_output.resolve()),
            "rows": len(trades),
            **file_evidence(args.trades_output),
        },
        "generator_identity": _generator_identity(),
        "decision": (
            "diagnostic_only; use actual canary fills or a routed wall-clock event "
            "replay before changing live execution"
        ),
    }
    write_immutable_json(args.output, report)
    return report


def _run_case(
    inputs: Hip3LifecycleCaseInputs,
    lifecycle: Hip3DeployedLifecycleSpec,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    windows = hip3_lifecycle_windows(inputs.report)
    recipe = configured_hip3_recipe(inputs.strategy_id)
    cells: list[Hip3DeployedLifecycleCell] = []
    for asset, friction in load_hip3_lifecycle_assets(inputs):
        signals = build_hip3_lifecycle_signals(asset.bars, recipe)
        cells.extend(
            evaluate_deployed_lifecycle(
                asset,
                friction,
                signals,
                windows,
                spec=lifecycle,
            )
        )
    evidence = {
        "path": str(inputs.report_path.resolve()),
        **file_evidence(inputs.report_path),
    }
    case = deployed_lifecycle_case_report(
        strategy_id=inputs.strategy_id,
        source_report=inputs.report,
        source_evidence=evidence,
        production_recipe=recipe,
        cells=cells,
        windows=windows,
        spec=lifecycle,
    )
    case["input_evidence"] = {
        "database_path": str(inputs.database_path.resolve()),
        "source_sidecar": hip3_file_reference(inputs.sidecar_path),
        "qualification_report": hip3_file_reference(inputs.qualification_path),
    }
    return case, lifecycle_trade_records(inputs.strategy_id, cells)


def _case_specs(values: list[str] | None) -> dict[str, Path]:
    if not values:
        return dict(_DEFAULT_CASES)
    output: dict[str, Path] = {}
    for raw in values:
        strategy, separator, path = raw.partition("=")
        if not separator or not strategy.strip() or not path.strip():
            raise ValueError("--case must use STRATEGY_ID=SOURCE_REPORT")
        if strategy in output:
            raise ValueError(f"duplicate HIP-3 diagnostic case: {strategy}")
        configured_hip3_recipe(strategy)
        output[strategy] = Path(path)
    return output


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/live/hip3_provider_recipes.py",
        root / "src/hypervector/research/hip3_deployed_lifecycle.py",
        root / "src/hypervector/research/hip3_deployed_lifecycle_reporting.py",
        root / "src/hypervector/research/hip3_lifecycle_inputs.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _trade_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame.from_records(rows)
    return pd.DataFrame(
        {
            "strategy_id": pd.Series(dtype=str),
            "symbol": pd.Series(dtype=str),
            "phase": pd.Series(dtype=str),
            "friction": pd.Series(dtype=str),
        }
    )


def _require_new_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable HIP-3 diagnostic outputs exist: {existing}")


def main() -> int:
    """Run the diagnostic and print a bounded summary."""
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
