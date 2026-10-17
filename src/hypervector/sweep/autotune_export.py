"""Strict strategy export from a successful measured tuning result.

Plugin-defined JSON mappings retain their legacy Any interface here.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.sizing import RiskConfig
from hypervector.sweep.autotune_sampling import _hypervelocity_exit_dict


def _export_settings(
    strategy_name: str, best_exit_dict: dict[str, object]
) -> tuple[ExitConfig, RiskConfig]:
    """Preserve strategy-managed exits and the exported sizing contract."""
    if is_hypervelocity_strategy(strategy_name):
        contract = HypervelocityContract()
        exit_cfg = ExitConfig(
            mode="fixed_rr",
            sl_pct=contract.target_price_fraction,
            rr=1.0,
        )
        risk_cfg = RiskConfig(
            risk_pct_min=contract.margin_fraction,
            risk_pct_max=contract.margin_fraction,
            max_size_frac=contract.notional_fraction,
        )
    else:
        exit_cfg = ExitConfig(
            **{k: v for k, v in best_exit_dict.items() if k != "leverage"}
        )
        risk_cfg = RiskConfig(max_size_frac=float(best_exit_dict.get("leverage", 1.0)))
    return exit_cfg, risk_cfg


def _export_autotune_candidate(
    *,
    root: Path,
    stamp: str,
    strategy_name: str,
    role: str,
    symbol: str,
    timeframe: str,
    lookback_days: int,
    fee_model: str,
    provenance: dict[str, Any],
    best_params: dict[str, Any],
    best_exit_dict: dict[str, Any],
    best_metrics: dict[str, Any],
) -> Path:
    """Write a strict Phase-2 bundle through the canonical exporter."""
    from hypervector.export.phase2 import export_candidate

    exit_cfg, risk_cfg = _export_settings(strategy_name, best_exit_dict)
    candidate_id = f"exp_{strategy_name}_{timeframe}_{stamp}"
    return export_candidate(
        root / "exports",
        run_id=stamp,
        meta={
            "track": role,
            "symbol": symbol,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "init_cash": 10_000.0,
            "tp_sl_mode": exit_cfg.mode,
            "exits": exit_cfg.to_dict(),
            "risk": risk_cfg.to_dict(),
            "costs": resolve_cost_model(fee_model).to_dict(),
            "apply_costs": True,
            "data_provenance": provenance,
            "fee_model": fee_model,
            "hypervelocity_contract": (
                _hypervelocity_exit_dict()
                if is_hypervelocity_strategy(strategy_name)
                else None
            ),
        },
        params={
            "strategy": strategy_name,
            "role": role,
            "exit_mode": exit_cfg.mode,
            **best_params,
        },
        metrics=best_metrics,
        candidate_id=candidate_id,
        strict=True,
    )
