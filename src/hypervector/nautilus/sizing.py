"""Map StrategyLoadout → ExitConfig / position size for Nautilus actors.

Reuses research formulas from ``hypervector.sweep.exits`` and
``hypervector.sweep.sizing`` — does not reimplement risk or exit math.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.sizing import (
    RiskConfig,
    risk_pct_from_conviction,
    size_frac_from_risk,
)
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)


def exit_config_from_loadout(loadout: StrategyLoadout) -> ExitConfig:
    """Build :class:`ExitConfig` from loadout exits dict + exit_mode fallback."""
    raw: dict[str, Any] = dict(loadout.exits or {})
    mode = raw.get("mode") or loadout.exit_mode or ExitConfig.mode
    defaults = ExitConfig()
    return ExitConfig(
        mode=str(mode),  # type: ignore[arg-type]
        sl_pct=float(raw.get("sl_pct", defaults.sl_pct)),
        rr=float(raw.get("rr", defaults.rr)),
        atr_length=int(raw.get("atr_length", defaults.atr_length)),
        sl_atr_mult=float(raw.get("sl_atr_mult", defaults.sl_atr_mult)),
        trail_atr_mult=float(raw.get("trail_atr_mult", defaults.trail_atr_mult)),
    )


def exit_config_from_dict(exits: dict[str, Any] | None) -> ExitConfig:
    """Build :class:`ExitConfig` from a (normalized) strategy-config exits dict."""
    raw = dict(exits or {})
    defaults = ExitConfig()
    return ExitConfig(
        mode=str(raw.get("mode", defaults.mode)),  # type: ignore[arg-type]
        sl_pct=float(raw.get("sl_pct", defaults.sl_pct)),
        rr=float(raw.get("rr", defaults.rr)),
        atr_length=int(raw.get("atr_length", defaults.atr_length)),
        sl_atr_mult=float(raw.get("sl_atr_mult", defaults.sl_atr_mult)),
        trail_atr_mult=float(raw.get("trail_atr_mult", defaults.trail_atr_mult)),
    )


def _risk_config_from_loadout(loadout: StrategyLoadout) -> RiskConfig:
    """Build :class:`RiskConfig` from loadout.risk with dataclass defaults."""
    raw: dict[str, Any] = dict(loadout.risk or {})
    defaults = RiskConfig()
    return RiskConfig(
        risk_pct_min=float(raw.get("risk_pct_min", defaults.risk_pct_min)),
        risk_pct_max=float(raw.get("risk_pct_max", defaults.risk_pct_max)),
        default_conviction=float(
            raw.get("default_conviction", defaults.default_conviction)
        ),
        max_size_frac=float(raw.get("max_size_frac", defaults.max_size_frac)),
    )


def position_size_frac(
    equity: float,
    stop_frac: float,
    loadout: StrategyLoadout,
    conviction: float,
) -> float:
    """Equity fraction to deploy from loadout risk band + stop distance.

    ``equity`` is accepted for API stability (notional conversion later);
    size is fraction-of-equity via existing sizing helpers.
    """
    del equity  # reserved for future notional conversion
    if is_hypervelocity_strategy(loadout.strategy_name):
        return HypervelocityContract().notional_fraction
    cfg = _risk_config_from_loadout(loadout)
    risk_pct = float(risk_pct_from_conviction(float(conviction), cfg))
    stop = pd.Series([float(stop_frac)])
    size = size_frac_from_risk(risk_pct, stop, cfg)
    return float(size.iloc[0])
