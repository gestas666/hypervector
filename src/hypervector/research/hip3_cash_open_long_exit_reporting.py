"""Report-only evidence for SPCX cash-open long exit challengers."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from hypervector.research.hip3_cash_open_long_exit_challenger import (
    CashOpenLongExitChallengerResult,
    CashOpenLongExitScenario,
)
from hypervector.research.hip3_oil_shock_reversion_reporting import (
    _fold_report,
    _partition_economics,
    _window,
)
from hypervector.research.hip3_opening_range_breakout_reporting import (
    opening_range_partition_trade_path_quality,
)
from hypervector.research.mu_hip3_candidate import summarize_trades


def build_cash_open_long_exit_report(
    result: CashOpenLongExitChallengerResult,
    development_bars: pd.DataFrame,
    *,
    preregistration: dict[str, object],
) -> dict[str, object]:
    """Serialize the frozen family without live or OOS authority."""
    scenarios = [result.control, *result.challengers]
    scenario_rows = [
        _scenario_report(item, development_bars, result.symbol) for item in scenarios
    ]
    selected = next(
        item
        for item in result.challengers
        if item.target_bps == result.selected_target_bps
    )
    all_paths_resolved = all(
        row["technical_path"]["status"] == "resolved" for row in scenario_rows
    )
    return {
        "schema_version": "hip3_cash_open_long_exit_challenger_v1",
        "symbol": result.symbol,
        "direction": "long",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "live_change_proposed": False,
        "preregistration": preregistration,
        "development_window": _window(result.control.development),
        "control": _scenario_summary(result.control, result.symbol),
        "challengers": [
            _scenario_summary(item, result.symbol) for item in result.challengers
        ],
        "scenarios": scenario_rows,
        "entry_identity_parity": _entry_identity_parity(result),
        "selection": _selection(result, selected),
        "research_disposition": _disposition(
            result.challenger_improves_control, all_paths_resolved
        ),
        "validation_accessed": result.validation_accessed,
        "holdout_accessed": result.holdout_accessed,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "limitations": _limitations(),
    }


def _scenario_report(
    scenario: CashOpenLongExitScenario,
    bars: pd.DataFrame,
    symbol: str,
) -> dict[str, object]:
    return {
        **_scenario_summary(scenario, symbol),
        "technical_path": opening_range_partition_trade_path_quality(
            bars, scenario.development
        ),
    }


def _scenario_summary(
    scenario: CashOpenLongExitScenario,
    symbol: str,
) -> dict[str, object]:
    return {
        "name": scenario.name,
        "target_policy": (
            "prior_cash_close" if scenario.target_bps is None else "entry_fixed_bps"
        ),
        "target_bps": scenario.target_bps,
        "development_economics": _partition_economics(scenario.development, symbol),
        "development_folds": [_fold_report(fold, symbol) for fold in scenario.folds],
        "exit_reasons": _exit_reasons(scenario),
    }


def _entry_identity_parity(
    result: CashOpenLongExitChallengerResult,
) -> dict[str, object]:
    entries = result.control.development.nominal.trades
    return {
        "status": "matched",
        "development_entries": len(entries),
        "scenario_count": 1 + len(result.challengers),
        "identity_fields": ["signal_time_utc", "entry_time_utc"],
    }


def _selection(
    result: CashOpenLongExitChallengerResult,
    selected: CashOpenLongExitScenario,
) -> dict[str, object]:
    stress = selected.development.stress
    diagnostics = summarize_trades(stress.trades)["all"]
    return {
        "development_selected_target_bps": result.selected_target_bps,
        "challenger_improves_control": result.challenger_improves_control,
        "positive_stress_folds": sum(
            fold.stress.net_pnl_usd > 0.0 for fold in selected.folds
        ),
        "worst_stress_fold_net_pnl_usd": min(
            fold.stress.net_pnl_usd for fold in selected.folds
        ),
        "stress_net_without_largest_winner_usd": (
            diagnostics.net_without_largest_winner_usd
        ),
        "stress_net_pnl_usd": stress.net_pnl_usd,
        "stress_maximum_drawdown_pct": stress.maximum_drawdown_pct,
        "selection_scope": "development_only",
    }


def _exit_reasons(scenario: CashOpenLongExitScenario) -> dict[str, dict[str, int]]:
    return {
        "nominal": dict(
            Counter(item.exit_reason for item in scenario.development.nominal.trades)
        ),
        "stress": dict(
            Counter(item.exit_reason for item in scenario.development.stress.trades)
        ),
    }


def _disposition(improves: bool, paths_resolved: bool) -> dict[str, object]:
    if not paths_resolved:
        status = "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
    elif improves:
        status = "DEVELOPMENT_CHALLENGER_ONLY_FORWARD_VALIDATION_REQUIRED"
    else:
        status = "REJECT_FIXED_TARGET_FAMILY_KEEP_CONTROL"
    return {
        "status": status,
        "technical_paths_resolved": paths_resolved,
        "challenger_improves_control": improves,
        "live_change_authorized": False,
    }


def _limitations() -> list[str]:
    return [
        "development-only hypothesis formation with validation and holdout sealed",
        "the candidate family was declared after one open forward path showed giveback",
        "long-only replay does not model cross-route shared-capital interactions",
        "same-bar ordering is liquidation, stop, then target",
        "intrabar target touch does not establish private queue priority",
        "no live strategy, exit, risk, sizing, or configuration change is authorized",
    ]
