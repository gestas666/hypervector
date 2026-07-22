"""Loadout → ExitConfig / position size helpers for Nautilus actor."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.nautilus.sizing import exit_config_from_loadout, position_size_frac


def _loadout(**overrides) -> StrategyLoadout:
    base = dict(
        strategy_name="test_strategy",
        role=None,
        params={},
        meta={},
        costs=None,
        risk=None,
        exit_mode=None,
        exits=None,
        export_dir=Path("/tmp"),
    )
    base.update(overrides)
    return StrategyLoadout(**base)


def test_exit_config_from_loadout_preserves_cli_overrides():
    loadout = _loadout(
        exits={
            "mode": "atr",
            "sl_atr_mult": 1.75,
            "rr": 2.5,
            "atr_length": 21,
            "sl_pct": 0.015,
            "trail_atr_mult": 2.5,
        }
    )
    cfg = exit_config_from_loadout(loadout)
    assert cfg.mode == "atr"
    assert cfg.sl_atr_mult == 1.75
    assert cfg.rr == 2.5
    assert cfg.atr_length == 21
    assert cfg.sl_pct == 0.015
    assert cfg.trail_atr_mult == 2.5


def test_exit_config_falls_back_to_loadout_exit_mode():
    loadout = _loadout(exit_mode="fixed_rr", exits={"sl_pct": 0.02, "rr": 3.0})
    cfg = exit_config_from_loadout(loadout)
    assert cfg.mode == "fixed_rr"
    assert cfg.sl_pct == 0.02
    assert cfg.rr == 3.0


def test_exit_config_defaults_when_exits_missing():
    loadout = _loadout(exits=None, exit_mode=None)
    cfg = exit_config_from_loadout(loadout)
    assert cfg.mode == "atr"
    assert cfg.sl_atr_mult == 1.5
    assert cfg.rr == 2.0


def test_position_size_frac_uses_risk_band():
    # risk 1–5%, conviction 0.5 → 3% risk; stop 1% → 3.0, capped by max_size_frac
    loadout = _loadout(
        risk={
            "risk_pct_min": 0.01,
            "risk_pct_max": 0.05,
            "max_size_frac": 5.0,
        }
    )
    size = position_size_frac(10_000.0, stop_frac=0.01, loadout=loadout, conviction=0.5)
    assert isinstance(size, float)
    assert size == pytest.approx(3.0)


def test_position_size_frac_clamped_by_max_size_frac():
    loadout = _loadout(
        risk={
            "risk_pct_min": 0.01,
            "risk_pct_max": 0.05,
            "max_size_frac": 1.0,
        }
    )
    size = position_size_frac(10_000.0, stop_frac=0.01, loadout=loadout, conviction=0.5)
    # 0.03 / 0.01 = 3.0 → clamped to 1.0
    assert size == pytest.approx(1.0)


def test_position_size_frac_defaults_when_risk_missing():
    loadout = _loadout(risk=None)
    # defaults: 1–5%, max_size_frac=1.0; conviction 0 → 1% risk / 2% stop = 0.5
    size = position_size_frac(10_000.0, stop_frac=0.02, loadout=loadout, conviction=0.0)
    assert size == pytest.approx(0.5)
