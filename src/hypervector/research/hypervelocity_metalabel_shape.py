"""Economic-shape diagnostics for observe-only loss-risk predictions."""

from __future__ import annotations

import math

import pandas as pd


def report_limitations(
    *,
    label_column: str,
    expected_resolved: int,
    expected_positives: int,
    fold_count: int = 3,
    exploration_scope: str = (
        "The same 90-day window remains exploration evidence, not a sealed holdout."
    ),
) -> list[str]:
    """Describe the statistical and execution limits of one report."""
    if fold_count < 1:
        raise ValueError("report limitation fold count must be positive")
    if label_column == "loss_risk":
        sample_limit = (
            f"Only {expected_resolved} resolved trades and {expected_positives} "
            "stop-or-liquidation loss labels are available across "
            f"{fold_count} folds."
        )
    else:
        sample_limit = (
            f"Only {expected_resolved} resolved trades and {expected_positives} "
            f"liquidation labels are available across {fold_count} folds."
        )
    return [
        sample_limit,
        "L2 MBP measures displayed depth, not private queue position or hidden liquidity.",
        "No candidate is calibrated or installed into runtime execution.",
        exploration_scope,
    ]


def population_summary(rows: pd.DataFrame, label_column: str) -> dict[str, int]:
    """Summarize resolved lifecycle states and the declared positive label."""
    statuses = rows["status"].value_counts()
    return {
        "resolved_trades": len(rows),
        "target_completed": int(statuses.get("target_completed", 0)),
        "stopped": int(statuses.get("stopped", 0)),
        "liquidated": int(statuses.get("liquidated", 0)),
        "positive_outcomes": int(rows[label_column].sum()),
    }


def _break_even_target_rate_pct() -> float:
    net_target = 8.0 - 2.0 * 0.00015 * 40.0 * 100.0
    net_stop_loss = 14.0 + (0.00015 + 0.00045) * 40.0 * 100.0
    return 100.0 * net_stop_loss / (net_stop_loss + net_target)


def _lowest_risk_fold(
    frame: pd.DataFrame,
    selection_fraction: float,
    break_even: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    count = max(1, math.ceil(selection_fraction * len(frame)))
    selected = frame.sort_values("prediction", kind="stable").head(count)
    target_rate = 100.0 * (1.0 - float(selected["loss_risk"].mean()))
    return selected, {
        "fold_id": int(frame["fold_id"].iloc[0]),
        "oos_samples": len(frame),
        "lowest_risk_samples": len(selected),
        "target_rate_pct": target_rate,
        "above_break_even": target_rate > break_even,
    }


def loss_risk_shape_diagnostics(
    predictions: pd.DataFrame,
    *,
    selection_fraction: float = 0.5,
) -> dict[str, object]:
    """Report fold-local target rates for the lowest predicted loss-risk half."""
    required = {"candidate", "fold_id", "loss_risk", "prediction"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"loss-risk predictions missing fields: {sorted(missing)}")
    if not 0.0 < selection_fraction <= 1.0:
        raise ValueError("loss-risk selection fraction must be within (0, 1]")
    break_even = _break_even_target_rate_pct()
    candidates: dict[str, object] = {}
    for name, candidate in predictions.groupby("candidate", sort=False):
        selected: list[pd.DataFrame] = []
        folds: list[dict[str, object]] = []
        for _, frame in candidate.groupby("fold_id", sort=True):
            chosen, row = _lowest_risk_fold(frame, selection_fraction, break_even)
            selected.append(chosen)
            folds.append(row)
        combined = pd.concat(selected, ignore_index=True)
        target_rate = 100.0 * (1.0 - float(combined["loss_risk"].mean()))
        candidates[str(name)] = {
            "oos_samples": len(candidate),
            "lowest_risk_samples": len(combined),
            "lowest_risk_target_rate_pct": target_rate,
            "folds_above_break_even": sum(
                bool(row["above_break_even"]) for row in folds
            ),
            "all_folds_above_break_even": all(
                bool(row["above_break_even"]) for row in folds
            ),
            "folds": folds,
        }
    return {
        "selection_fraction": selection_fraction,
        "theoretical_break_even_target_rate_pct": break_even,
        "candidates": candidates,
    }
