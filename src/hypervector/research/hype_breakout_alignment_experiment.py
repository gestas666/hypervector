"""Post-hoc HYPE structural-versus-breakout entry-alignment diagnostic."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

import pandas as pd

from hypervector.research.hype_breakout_exit_experiment import (
    split_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)

AlignmentCohort = Literal["control", "aligned_only", "opposed_only"]
_COHORTS: tuple[AlignmentCohort, ...] = (
    "control",
    "aligned_only",
    "opposed_only",
)
_SIDES = frozenset({"long", "short"})


def build_hype_breakout_alignment_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
) -> dict[str, object]:
    """Compare structural entries by 5m breakout-direction agreement."""
    masks, accounting = _alignment_masks(market)
    config = HypeExitReplayConfig(
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )
    development: dict[str, object] = {}
    opened_final: dict[str, object] = {}
    split: dict[str, object] | None = None
    for cohort in _COHORTS:
        candidate = market.copy(deep=False)
        candidate["entry_side"] = market["entry_side"].where(masks[cohort], None)
        dev, final, current_split = split_hype_exit_market(
            candidate,
            config,
            holdout_days,
        )
        if split is not None and split != current_split:
            raise RuntimeError("HYPE alignment cohorts produced different splits")
        split = current_split
        development[cohort] = _period_report(dev, config)
        opened_final[cohort] = _period_report(final, config)
    return _artifact(
        accounting,
        split or {},
        config,
        development,
        opened_final,
    )


def _alignment_masks(
    market: pd.DataFrame,
) -> tuple[dict[AlignmentCohort, pd.Series], dict[str, int]]:
    required = {"entry_side", "breakout_side"}
    missing = sorted(required.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE alignment market missing columns: {missing}")
    entry = market["entry_side"]
    breakout = market["breakout_side"]
    _validate_sides(entry, "entry_side")
    _validate_sides(breakout, "breakout_side")
    raw = entry.isin(_SIDES)
    available = raw & breakout.isin(_SIDES)
    aligned = available & entry.eq(breakout)
    opposed = available & entry.ne(breakout)
    masks: dict[AlignmentCohort, pd.Series] = {
        "control": raw,
        "aligned_only": aligned,
        "opposed_only": opposed,
    }
    accounting = {
        "raw_structural_onsets": int(raw.sum()),
        "breakout_side_attributable": int(available.sum()),
        "aligned_onsets": int(aligned.sum()),
        "opposed_onsets": int(opposed.sum()),
        "unavailable_onsets": int((raw & ~available).sum()),
    }
    return masks, accounting


def _validate_sides(values: pd.Series, label: str) -> None:
    invalid = values.notna() & ~values.isin(_SIDES)
    if invalid.any():
        raise ValueError(f"HYPE alignment {label} contains unsupported values")


def _period_report(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("entry_alignment_diagnostic"),
        config,
    )
    return _metrics(report)


def _metrics(report: HypeExitReplayReport) -> dict[str, object]:
    completed = report.completed_trades
    return {
        "completed_trades": completed,
        "wins": report.wins,
        "losses": report.losses,
        "win_rate": report.wins / completed if completed else None,
        "net_return_bps": report.net_return_bps,
        "mean_net_return_bps_per_trade": (
            report.net_return_bps / completed if completed else None
        ),
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "total_fee_bps": report.total_fee_bps,
        "funding_bps": report.funding_bps,
        "occupied_signals": report.occupied_signals,
        "exit_reasons": report.exit_reasons,
    }


def _artifact(
    accounting: dict[str, int],
    split: dict[str, object],
    config: HypeExitReplayConfig,
    development: dict[str, object],
    opened_final: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "mode": "hype_breakout_entry_alignment_post_hoc_v2",
        "execution_authority": "none",
        "report_only": True,
        "contract": {
            "entry_side_source": "completed_1h_sma10_sma30_relation",
            "alignment_source": "completed_5m_breakout_direction",
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
            "performance_gate": False,
            "comparison_unit": "mean_net_return_bps_per_completed_trade",
            "execution": asdict(config),
        },
        "entry_accounting": accounting,
        "split": split,
        "trial_accounting": {"post_hoc_cohorts": len(_COHORTS)},
        "development": development,
        "holdout_already_opened": opened_final,
        "development_comparison": _comparisons(development),
        "holdout_comparison": _comparisons(opened_final),
        "limitations": [
            "alignment cohorts were defined after inspecting the current live conflict",
            "the final 60-day block was already opened and is descriptive only",
            "net_return_bps is cumulative and not directly comparable across unequal counts",
            "different retained signals change subsequent position occupancy",
            "one-minute bars and fixed slippage do not prove live IOC fills",
            "this comparison cannot filter, size, route, retain, or close a trade",
        ],
    }


def _comparisons(values: dict[str, object]) -> dict[str, float | None]:
    control = _result(values, "control")
    aligned = _result(values, "aligned_only")
    opposed = _result(values, "opposed_only")
    return {
        "aligned_minus_control_net_bps": _net(aligned) - _net(control),
        "opposed_minus_control_net_bps": _net(opposed) - _net(control),
        "opposed_minus_aligned_net_bps": _net(opposed) - _net(aligned),
        "aligned_minus_control_mean_net_bps_per_trade": _difference(
            aligned,
            control,
        ),
        "opposed_minus_control_mean_net_bps_per_trade": _difference(
            opposed,
            control,
        ),
        "opposed_minus_aligned_mean_net_bps_per_trade": _difference(
            opposed,
            aligned,
        ),
    }


def _result(values: dict[str, object], key: str) -> dict[str, object]:
    value = values[key]
    if not isinstance(value, dict):
        raise RuntimeError(f"HYPE alignment result {key} is not an object")
    return value


def _net(value: dict[str, object]) -> float:
    result = value["net_return_bps"]
    if isinstance(result, bool) or not isinstance(result, (float, int)):
        raise RuntimeError("HYPE alignment net return is not numeric")
    return float(result)


def _difference(left: dict[str, object], right: dict[str, object]) -> float | None:
    left_value = _optional_number(left, "mean_net_return_bps_per_trade")
    right_value = _optional_number(right, "mean_net_return_bps_per_trade")
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _optional_number(value: dict[str, object], key: str) -> float | None:
    result = value[key]
    if result is None:
        return None
    if isinstance(result, bool) or not isinstance(result, (float, int)):
        raise RuntimeError(f"HYPE alignment {key} is not numeric")
    return float(result)
