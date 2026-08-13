#!/usr/bin/env python3
"""Run the preregistered three-arm HIP-3 early-adverse exit experiment."""

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
from hypervector.live.hip3_cohort_providers import HIP3_SWING_COMMODITY_STRATEGY
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
from hypervector.research.hip3_early_adverse_exit import (
    Hip3ExitPolicyArm,
    build_exit_policy_comparison,
)
from hypervector.research.hip3_lifecycle_inputs import (
    Hip3LifecycleCaseInputs,
    Recipe,
    build_hip3_lifecycle_signals,
    hip3_file_reference,
    hip3_lifecycle_windows,
    load_hip3_lifecycle_assets,
    load_hip3_lifecycle_case_inputs,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)

_DEFAULT_SOURCE = Path(
    "data/logs/research/hip3_swing_ha_transfer_sndk_gold_disabled_brent_v1.json"
)
_DEFAULT_OUTPUT = Path("data/logs/research/hip3_early_adverse_ha_flip_20260809.json")
_DEFAULT_TRADES = Path(
    "data/logs/research/hip3_early_adverse_ha_flip_20260809.trades.parquet"
)
_POLICIES = ("ignore", "honor", "early_adverse")


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable, non-executable experiment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate all fixed arms and publish content-addressed evidence."""
    _require_new_outputs(args.output, args.trades_output)
    inputs = load_hip3_lifecycle_case_inputs(
        HIP3_SWING_COMMODITY_STRATEGY,
        args.source,
    )
    recipe = configured_hip3_recipe(HIP3_SWING_COMMODITY_STRATEGY)
    assets = load_hip3_lifecycle_assets(inputs)
    windows = hip3_lifecycle_windows(inputs.report)
    arms: dict[str, Hip3ExitPolicyArm] = {}
    cases: dict[str, object] = {}
    rows: list[dict[str, object]] = []
    for policy in _POLICIES:
        spec = Hip3DeployedLifecycleSpec(signal_exit_policy=policy)
        cells = _evaluate_arm(assets, recipe, windows, spec)
        arms[policy] = Hip3ExitPolicyArm(spec, cells)
        cases[policy] = _case_report(inputs, recipe, windows, spec, cells)
        rows.extend(
            {"exit_policy": policy, **row}
            for row in lifecycle_trade_records(
                HIP3_SWING_COMMODITY_STRATEGY,
                cells,
            )
        )
    trades = _trade_frame(rows)
    report = _report(inputs, cases, arms, windows, args.trades_output, len(trades))
    write_immutable_parquet(args.trades_output, trades)
    report["trade_sidecar"] = {
        "path": str(args.trades_output.resolve()),
        "rows": len(trades),
        **file_evidence(args.trades_output),
    }
    write_immutable_json(args.output, report)
    return report


def _evaluate_arm(
    assets: tuple[tuple[Hip3TransferAsset, Hip3ExecutionFriction], ...],
    recipe: Recipe,
    windows: Hip3TransferWindows,
    spec: Hip3DeployedLifecycleSpec,
) -> tuple[Hip3DeployedLifecycleCell, ...]:
    cells: list[Hip3DeployedLifecycleCell] = []
    for asset, friction in assets:
        signals = build_hip3_lifecycle_signals(asset.bars, recipe)
        cells.extend(
            evaluate_deployed_lifecycle(
                asset,
                friction,
                signals,
                windows,
                spec=spec,
            )
        )
    return tuple(cells)


def _case_report(
    inputs: Hip3LifecycleCaseInputs,
    recipe: Recipe,
    windows: Hip3TransferWindows,
    spec: Hip3DeployedLifecycleSpec,
    cells: tuple[Hip3DeployedLifecycleCell, ...],
) -> dict[str, object]:
    return deployed_lifecycle_case_report(
        strategy_id=inputs.strategy_id,
        source_report=inputs.report,
        source_evidence=hip3_file_reference(inputs.report_path),
        production_recipe=recipe,
        cells=cells,
        windows=windows,
        spec=spec,
    )


def _report(
    inputs: Hip3LifecycleCaseInputs,
    cases: dict[str, object],
    arms: dict[str, Hip3ExitPolicyArm],
    windows: Hip3TransferWindows,
    trades_output: Path,
    trade_rows: int,
) -> dict[str, object]:
    return {
        "schema_version": "hip3_early_adverse_ha_flip_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "strategy_id": HIP3_SWING_COMMODITY_STRATEGY,
        "hypothesis": {
            "policy_id": "early_adverse_8bar_mfe20_adverse13",
            "maximum_age_bars": 8,
            "maximum_mfe_bps": 20.0,
            "minimum_adverse_bps": 13.0,
            "signal_time": "completed_15m_bar_close",
            "execution_time": "next_modeled_open",
        },
        "source_report": hip3_file_reference(inputs.report_path),
        "input_evidence": {
            "database_path": str(inputs.database_path.resolve()),
            "source_sidecar": hip3_file_reference(inputs.sidecar_path),
            "qualification_report": hip3_file_reference(inputs.qualification_path),
        },
        "cases": cases,
        "comparison": build_exit_policy_comparison(arms),
        "holdout": {
            "status": "sealed_not_evaluated",
            "start_utc": windows.validation_end_utc.isoformat(),
            "end_utc": windows.holdout_end_utc.isoformat(),
            "metrics_accessed": False,
        },
        "pending_trade_sidecar": {
            "path": str(trades_output.resolve()),
            "rows": trade_rows,
        },
        "generator_identity": _generator_identity(),
        "decision": "evidence_pending_review; no automatic live change",
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_deployed_lifecycle.py",
        root / "src/hypervector/research/hip3_early_adverse_exit.py",
        root / "src/hypervector/research/shared_bar_portfolio.py",
        root / "src/hypervector/research/shared_portfolio_signal_exits.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _trade_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame.from_records(rows)
    return pd.DataFrame(
        {
            "exit_policy": pd.Series(dtype=str),
            "strategy_id": pd.Series(dtype=str),
            "symbol": pd.Series(dtype=str),
            "phase": pd.Series(dtype=str),
            "friction": pd.Series(dtype=str),
        }
    )


def _require_new_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable HIP-3 exit outputs exist: {existing}")


def main() -> int:
    """Run the experiment and print only its immutable output identity."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "trade_rows": report["trade_sidecar"]["rows"],
                "execution_authority": "none",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
