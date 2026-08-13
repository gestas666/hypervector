"""Predeclared low-exposure Hypervelocity maker-replay candidates."""

from __future__ import annotations

from hypervector.research.maker_replay_models import FillRule, MakerReplayConfig

_TARGET_PRICE_FRACTION = 8.0 / 30.0 / 100.0
_STOP_PRICE_FRACTION = 60.0 / 10_000.0


def measured_hypervelocity_candidate_configs(
    *,
    initial_equity: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return the frozen control and low-exposure comparison matrix."""
    candidates = (
        ("alloc35_lev30_control", 0.35, 30.0, False),
        ("alloc05_lev03_no_stop", 0.05, 3.0, False),
        ("alloc05_lev03_stop60", 0.05, 3.0, True),
        ("alloc10_lev05_no_stop", 0.10, 5.0, False),
        ("alloc10_lev05_stop60", 0.10, 5.0, True),
    )
    return {
        name: _candidate_config(
            initial_equity=initial_equity,
            fill_rule=fill_rule,
            margin_fraction=margin_fraction,
            leverage=leverage,
            stopped=stopped,
        )
        for name, margin_fraction, leverage, stopped in candidates
    }


def _candidate_config(
    *,
    initial_equity: float,
    fill_rule: FillRule,
    margin_fraction: float,
    leverage: float,
    stopped: bool,
) -> MakerReplayConfig:
    target_margin_pct = _TARGET_PRICE_FRACTION * leverage * 100.0
    stop_margin_pct = _STOP_PRICE_FRACTION * leverage * 100.0 if stopped else None
    return MakerReplayConfig(
        initial_equity=initial_equity,
        margin_fraction=margin_fraction,
        leverage=leverage,
        target_margin_pct=target_margin_pct,
        fill_rule=fill_rule,
        entry_ttl_seconds=60.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        fixed_margin_stop_pct=stop_margin_pct,
        maximum_hold_seconds=86_400.0,
        occupied_signal_policy="ignore",
    )
