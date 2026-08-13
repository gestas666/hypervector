"""Predeclared stop/hold robustness on backward SOL validation history."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

import pandas as pd

from hypervector.research.range_onset_signals import build_range_onset_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.sol_range_onset_backward_challenge import (
    PreparedGapBlock,
    aggregate_reset_block_reports,
    load_verified_sol_backward_inputs,
    prepare_gap_safe_blocks,
)
from hypervector.research.sol_range_onset_backward_evidence import sha256

SignalBuilder = Callable[[pd.DataFrame], pd.DataFrame]
_STOP_BPS = (40.0, 60.0, 80.0, 100.0)
_HOLD_HOURS: tuple[int | None, ...] = (24, 48, 96, None)


@dataclass(frozen=True)
class BackwardShape:
    """One stop and maximum-hold cell declared before backward validation."""

    stop_bps: float
    max_hold_hours: int | None

    @property
    def trial_id(self) -> str:
        """Return the stable identity shared with the prior shape surface."""
        hold = "none" if self.max_hold_hours is None else str(self.max_hold_hours)
        return f"stop={self.stop_bps:g}__hold={hold}"


@dataclass(frozen=True)
class PreparedBackwardShapeBlock:
    """One gap-safe execution block with signals computed after causal warm-up."""

    number: int
    start: pd.Timestamp
    end: pd.Timestamp
    gap_fill_rows: int
    bars: pd.DataFrame
    signals: pd.DataFrame


def shape_grid() -> tuple[BackwardShape, ...]:
    """Return the exact 16-cell stop/hold surface declared on the later year."""
    return tuple(
        BackwardShape(stop, hold) for stop, hold in product(_STOP_BPS, _HOLD_HOURS)
    )


def load_predeclared_shape_grid(
    path: Path,
    shapes: tuple[BackwardShape, ...],
) -> dict[str, object]:
    """Prove the tested cells existed in the immutable prior surface."""
    payload = _read_object(path)
    expected = {
        "mode": "multi_asset_range_onset_shape_surface_post_hoc_report_only",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("prior SOL shape-surface identity mismatch")
    continuous = _object_map(payload.get("continuous"), "continuous surface")
    trials = _object_list(continuous.get("trials"), "continuous trials")
    observed = {_trial_id(row) for row in trials}
    required = {shape.trial_id for shape in shapes}
    if observed != required:
        raise ValueError("prior SOL shape surface does not match the requested grid")
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "trial_count": len(observed),
        "trial_ids": sorted(observed),
    }


def prepare_backward_shape_blocks(
    blocks: tuple[PreparedGapBlock, ...],
    funding: pd.Series,
    *,
    signal_builder: SignalBuilder = build_range_onset_signals,
    warmup_hours: int = 30,
) -> tuple[list[PreparedBackwardShapeBlock], list[dict[str, object]]]:
    """Attach funding and compute signals once per gap-safe block."""
    prepared: list[PreparedBackwardShapeBlock] = []
    skipped: list[dict[str, object]] = []
    for block in blocks:
        execution_start = block.start + pd.Timedelta(hours=warmup_hours)
        enriched = _attach_funding(block.bars, funding)
        execution = enriched.loc[enriched.index >= execution_start]
        if len(execution) < 2:
            skipped.append(_skipped_block(block, execution_start))
            continue
        signals = signal_builder(enriched).loc[execution.index]
        prepared.append(
            PreparedBackwardShapeBlock(
                block.number,
                block.start,
                block.end,
                block.gap_fill_rows,
                execution,
                signals,
            )
        )
    return prepared, skipped


def evaluate_backward_shapes(
    blocks: list[PreparedBackwardShapeBlock],
    shapes: tuple[BackwardShape, ...],
) -> list[dict[str, object]]:
    """Retain every shape result, including negative and censored cells."""
    return [_evaluate_shape(blocks, shape) for shape in shapes]


def evaluate_sol_backward_shape_surface(
    *,
    bars_path: Path,
    funding_path: Path,
    predeclared_surface_path: Path,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    """Build one checksum-linked, report-only backward robustness surface."""
    shapes = shape_grid()
    declaration = load_predeclared_shape_grid(predeclared_surface_path, shapes)
    bars, funding = load_verified_sol_backward_inputs(
        bars_path=bars_path,
        funding_path=funding_path,
        start=start,
        end=end,
    )
    gap_blocks = prepare_gap_safe_blocks(bars, max_gap_minutes=30)
    blocks, skipped = prepare_backward_shape_blocks(gap_blocks, funding)
    trials = evaluate_backward_shapes(blocks, shapes)
    return _artifact(
        bars_path,
        funding_path,
        declaration,
        start,
        end,
        bars,
        skipped,
        trials,
    )


def _evaluate_shape(
    blocks: list[PreparedBackwardShapeBlock],
    shape: BackwardShape,
) -> dict[str, object]:
    block_rows: list[dict[str, object]] = []
    complete: list[SharedPortfolioReport] = []
    config = _risk_config(shape)
    for block in blocks:
        report = evaluate_shared_bar_portfolio(block.bars, block.signals, config)
        status = "censored_end_boundary" if report.forced_end_exits else "complete"
        block_rows.append(_block_result(block, status, report))
        if status == "complete":
            complete.append(report)
    return {
        "trial_id": shape.trial_id,
        "shape": asdict(shape),
        "execution_authority": "none",
        "complete_block_count": len(complete),
        "censored_block_count": len(blocks) - len(complete),
        "blocks": block_rows,
        "aggregate": aggregate_reset_block_reports(complete),
    }


def _risk_config(shape: BackwardShape) -> SharedPortfolioConfig:
    hold = None if shape.max_hold_hours is None else shape.max_hold_hours * 60
    return SharedPortfolioConfig(
        symbol="SOL",
        initial_equity=15_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        venue_max_leverage=20.0,
        stop_margin_pct=shape.stop_bps * 5.0 / 100.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=2.0,
        market_exit_slippage_bps=2.0,
        max_hold_bars=hold,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=True,
    )


def _attach_funding(bars: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    enriched = bars.copy()
    enriched["funding_rate"] = 0.0
    common = enriched.index.intersection(funding.index)
    enriched.loc[common, "funding_rate"] = funding.loc[common].to_numpy()
    return enriched


def _skipped_block(
    block: PreparedGapBlock,
    execution_start: pd.Timestamp,
) -> dict[str, object]:
    return {
        "block": block.number,
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "execution_start_utc": execution_start.isoformat(),
        "status": "insufficient_warmup",
    }


def _block_result(
    block: PreparedBackwardShapeBlock,
    status: str,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    return {
        "block": block.number,
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "gap_fill_rows": block.gap_fill_rows,
        "status": status,
        "metrics": report.to_dict(),
    }


def _artifact(
    bars_path: Path,
    funding_path: Path,
    declaration: dict[str, object],
    start: datetime,
    end: datetime,
    bars: pd.DataFrame,
    skipped: list[dict[str, object]],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_backward_predeclared_shape_surface_bar_only",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "place_attempted": False,
        "submitted": False,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "trial_count": len(trials),
        "predeclaration_evidence": declaration,
        "data_evidence": _data_evidence(bars_path, funding_path, bars),
        "skipped_blocks": skipped,
        "trials": trials,
        "limitations": _limitations(),
    }


def _data_evidence(
    bars_path: Path,
    funding_path: Path,
    bars: pd.DataFrame,
) -> dict[str, object]:
    deltas = bars["timestamp"].diff().dropna()
    missing = deltas[deltas > pd.Timedelta(minutes=1)] / pd.Timedelta(minutes=1) - 1
    return {
        "bars_path": str(bars_path.resolve()),
        "bars_sha256": sha256(bars_path),
        "bars_manifest_sha256": sha256(bars_path.parent / "manifest.json"),
        "raw_bar_rows": len(bars),
        "source_missing_minutes": int(missing.sum()),
        "source_outages_above_30m": int(missing.gt(30).sum()),
        "funding_path": str(funding_path.resolve()),
        "funding_sha256": sha256(funding_path),
        "funding_manifest_sha256": sha256(funding_path.parent / "manifest.json"),
    }


def _limitations() -> list[str]:
    return [
        "the rule was selected on the later year and this is backward validation",
        "all 16 cells were declared before this backward window was acquired",
        "results remain bar-only until challenged with finite L2 and public trades",
        "large provider outages split independently reset blocks",
        "cells are observations rather than implicit promotion or rejection gates",
    ]


def _read_object(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"prior SOL shape surface is missing: {path}")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("prior SOL shape surface contains invalid JSON") from exc
    return _object_map(payload, "shape surface")


def _object_map(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"SOL backward {label} must be a string-keyed object")
    return value


def _object_list(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"SOL backward {label} must be a list")
    return [_object_map(row, label) for row in value]


def _trial_id(row: Mapping[str, object]) -> str:
    value = row.get("trial_id")
    if not isinstance(value, str) or not value:
        raise ValueError("prior SOL shape trial is missing trial_id")
    return value
