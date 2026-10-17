"""Strict strategy export from a successful measured tuning result.

Plugin-defined JSON mappings retain their legacy Any interface here.
"""

from __future__ import annotations
from pathlib import Path
from hypervector.export.phase2 import export_candidate
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
) -> tuple[dict[str, Any], str, RiskConfig]:
    """Return the measured exit lifecycle, its mode and the sizing contract.

    Hypervelocity is measured with strategy-managed exits and no stop, so it
    exports ``strategy_target_only`` rather than a symmetric stop at the target.
    """
    if is_hypervelocity_strategy(strategy_name):
        contract = HypervelocityContract()
        exits = _hypervelocity_exit_dict()
        risk_cfg = RiskConfig(
            risk_pct_min=contract.margin_fraction,
            risk_pct_max=contract.margin_fraction,
            max_size_frac=contract.notional_fraction,
        )
        return exits, str(exits["mode"]), risk_cfg
    exit_cfg = ExitConfig(
        **{k: v for k, v in best_exit_dict.items() if k != "leverage"}  # type: ignore[arg-type]
    )
    risk_cfg = RiskConfig(max_size_frac=float(best_exit_dict.get("leverage", 1.0)))  # type: ignore[arg-type]
    return exit_cfg.to_dict(), exit_cfg.mode, risk_cfg


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
    evaluation: dict[str, Any] | None = None,
    fee_model_requested: str | None = None,
) -> Path:
    """Write a strict Phase-2 bundle through the canonical exporter.

    ``meta.conviction`` is the conviction the trials were sized with (the
    risk contract's default; autotune does not search conviction), so
    ``nautilus run`` replays the measured sizing. ``meta.instrument`` comes
    from cached venue metadata under ``root`` (see ``export.venue_meta``).
    """
    exits, mode, risk_cfg = _export_settings(strategy_name, best_exit_dict)
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
            "tp_sl_mode": mode,
            "exits": exits,
            "risk": risk_cfg.to_dict(),
            "costs": resolve_cost_model(fee_model).to_dict(),
            "apply_costs": True,
            "data_provenance": provenance,
            "fee_model": fee_model,
            "fee_model_requested": fee_model_requested or fee_model,
            "conviction": risk_cfg.default_conviction,
            "hypervelocity_contract": (
                _hypervelocity_exit_dict()
                if is_hypervelocity_strategy(strategy_name)
                else None
            ),
            "evaluation": evaluation,
        },
        params={
            "strategy": strategy_name,
            "role": role,
            "exit_mode": mode,
            **best_params,
        },
        metrics=best_metrics,
        candidate_id=candidate_id,
        strict=True,
        data_root=root,
    )
