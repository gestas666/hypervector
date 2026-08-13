"""Predeclared allocation/leverage surface for BTC maker research."""

from __future__ import annotations

from dataclasses import replace

from hypervector.research.maker_replay_models import FillRule, MakerReplayConfig

ALLOCATION_FRACTIONS = (0.50, 0.70, 1.00)
LEVERAGES = (10.0, 20.0, 30.0, 40.0)


def _candidate_name(margin_fraction: float, leverage: float) -> str:
    allocation = int(round(margin_fraction * 100.0))
    leverage_int = int(round(leverage))
    suffix = "_control" if (allocation, leverage_int) == (70, 40) else ""
    return f"alloc{allocation}_lev{leverage_int}{suffix}"


def risk_surface_candidate_configs(
    *,
    initial_equity: float,
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return every frozen BTC allocation/leverage surface candidate."""
    return {
        _candidate_name(margin_fraction, leverage): MakerReplayConfig(
            initial_equity=initial_equity,
            margin_fraction=margin_fraction,
            leverage=leverage,
            target_margin_pct=8.0,
            fill_rule=fill_rule,
            entry_ttl_seconds=entry_eligibility_seconds,
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="regime_reset",
        )
        for margin_fraction in ALLOCATION_FRACTIONS
        for leverage in LEVERAGES
    }


def selected_peak_candidate_configs(
    *,
    initial_equity: float,
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return frozen 30x leaders with and without the +7% peak lock."""
    surface = risk_surface_candidate_configs(
        initial_equity=initial_equity,
        entry_eligibility_seconds=entry_eligibility_seconds,
        fill_rule=fill_rule,
    )
    result: dict[str, MakerReplayConfig] = {}
    for allocation in (50, 70):
        name = f"alloc{allocation}_lev30"
        base = surface[name]
        result[name] = base
        result[f"{name}_peak7"] = replace(
            base,
            peak_protection_activation_margin_pct=7.0,
            peak_protection_lock_ratio=0.55,
            peak_protection_minimum_price_move_fraction=0.0005,
            peak_protection_update_cooldown_seconds=60.0,
        )
    result["alloc70_lev40_control"] = surface["alloc70_lev40_control"]
    return result


def selected_sizing_candidate_configs(
    *,
    initial_equity: float,
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return the frozen 30x sizing candidates and faithful 40x control."""
    surface = risk_surface_candidate_configs(
        initial_equity=initial_equity,
        entry_eligibility_seconds=entry_eligibility_seconds,
        fill_rule=fill_rule,
    )
    names = ("alloc50_lev30", "alloc70_lev30", "alloc70_lev40_control")
    return {name: surface[name] for name in names}
