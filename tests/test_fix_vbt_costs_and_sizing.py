"""Regression: honest cost defaults, reported effective risk, grid direction tags."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.registry import (
    StrategySpec,
    clear_registry,
    get_strategy,
    normalize_direction,
)
from hypervector.sweep import costs
from hypervector.sweep.costs import (
    COST_MODEL_ALIASES,
    COST_MODEL_DESCRIPTIONS,
    COST_MODEL_NAMES,
    HL_BASE_TAKER,
    HL_VIP1_TAKER,
    ZERO_COST,
    canonical_cost_model_name,
    resolve_cost_model,
)
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.search import run_grid_search
from hypervector.sweep.sizing import RiskConfig


# --- fee model naming and engine defaults -----------------------------------


def test_engine_default_cost_is_the_base_taker_rate() -> None:
    df = fixture_ohlcv(n_bars=300, drift=5.0, wave_period=30)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[40] = True
    exits.iloc[120] = True

    m = compute_trial_metrics(df["close"], entries, exits, df=df)

    assert m["fees"] == HL_BASE_TAKER.taker_fee == 0.00045
    assert m["slippage_bps"] == HL_BASE_TAKER.slippage_bps == 2.0


def test_grid_search_default_cost_is_the_base_taker_rate() -> None:
    df = fixture_ohlcv(n_bars=400, drift=5.0, wave_period=30)
    spec = StrategySpec(
        name="probe_long",
        role="uptrend",
        param_grid={},
        build_signals=lambda frame: (
            pd.Series([i % 50 == 5 for i in range(len(frame))], index=frame.index),
            pd.Series([i % 50 == 25 for i in range(len(frame))], index=frame.index),
            "long",
        ),
    )

    [result] = run_grid_search(df, spec)

    assert result.status == "ok"
    assert result.metrics["fees"] == HL_BASE_TAKER.taker_fee


def test_legacy_taker_default_alias_is_documented_as_tier_two_not_base() -> None:
    # Historical labels keep their meaning: the alias still resolves to 3.5 bps.
    assert resolve_cost_model("hl_taker_default") is HL_VIP1_TAKER
    assert canonical_cost_model_name("hl_taker_default") == "hl_vip1_taker"
    assert canonical_cost_model_name("HL-Taker-Default") == "hl_vip1_taker"
    assert canonical_cost_model_name(None) == "hl_base_taker"
    assert canonical_cost_model_name("default") == "hl_base_taker"
    assert "hl_taker_default" in costs.LEGACY_COST_MODEL_ALIASES
    assert "not the base" in costs.LEGACY_COST_MODEL_ALIASES["hl_taker_default"]
    assert "tier 2" in COST_MODEL_DESCRIPTIONS["hl_vip1_taker"]
    assert "4.5 bps" in COST_MODEL_DESCRIPTIONS["hl_base_taker"]
    assert set(COST_MODEL_DESCRIPTIONS) == set(COST_MODEL_NAMES)
    assert set(costs.LEGACY_COST_MODEL_ALIASES) <= set(COST_MODEL_ALIASES)
    with pytest.raises(ValueError, match="unknown fee model"):
        canonical_cost_model_name("hl_taker_defualt")


def test_cost_module_docstring_does_not_call_3_5_bps_vip1() -> None:
    doc = costs.__doc__ or ""
    assert "VIP 1 Taker Fee: 3.5" not in doc
    assert "tier 2" in doc.lower()


# --- conviction / risk sizing transparency -----------------------------------


def _atr_trial(
    conviction: float,
    *,
    max_size_frac: float = 1.0,
    exit_cfg: ExitConfig = ExitConfig(mode="atr", sl_atr_mult=1.5, rr=50.0),
) -> dict:
    df = fixture_ohlcv(n_bars=600, drift=3.0, wave_period=60)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[[100, 300]] = True
    exits.iloc[[150, 350]] = True
    return compute_trial_metrics(
        df["close"],
        entries,
        exits,
        df=df,
        cost=ZERO_COST,
        exit_cfg=exit_cfg,
        risk_cfg=RiskConfig(max_size_frac=max_size_frac),
        conviction=conviction,
    )


def test_effective_risk_is_reported_when_the_size_cap_binds() -> None:
    low, high = _atr_trial(0.0), _atr_trial(1.0)

    # requested risk is reported unchanged (back-compat) ...
    assert low["avg_risk_pct"] == pytest.approx(1.0)
    assert high["avg_risk_pct"] == pytest.approx(5.0)
    assert low["requested_risk_pct"] == pytest.approx(1.0)
    # ... but the tight ATR stop makes the 1x cap bind for every entry,
    # so the realised risk is identical and far below the request.
    assert low["size_cap_bound_fraction"] == pytest.approx(1.0)
    assert high["size_cap_bound_fraction"] == pytest.approx(1.0)
    assert low["effective_risk_pct"] == pytest.approx(high["effective_risk_pct"], rel=1e-9)
    assert 0.0 < high["effective_risk_pct"] < 1.0
    assert low["net_pnl"] == pytest.approx(high["net_pnl"], rel=1e-9)


def test_effective_risk_matches_request_when_the_cap_does_not_bind() -> None:
    # 1% risk / 0.5% stop = 2x, below a 5x leverage cap
    wide = ExitConfig(mode="fixed_rr", sl_pct=0.005, rr=50.0)
    m = _atr_trial(0.0, max_size_frac=5.0, exit_cfg=wide)

    assert m["size_cap_bound_fraction"] == pytest.approx(0.0)
    assert m["effective_risk_pct"] == pytest.approx(1.0, rel=1e-9)
    assert m["max_position_leverage"] == pytest.approx(2.0, rel=1e-9)


# --- direction tags from strategy builders -----------------------------------


def test_normalize_direction() -> None:
    assert normalize_direction("long") == "long"
    assert normalize_direction(" SHORT ") == "short"
    assert normalize_direction("impulse_1m_long") == "long"
    assert normalize_direction("impulse_1m_range_short") == "short"
    for bad in ("", "both", "longshort", "shortish", None, "flat"):
        with pytest.raises(ValueError, match="direction"):
            normalize_direction(bad)  # type: ignore[arg-type]


def test_grid_search_runs_impulse_strategies_with_tagged_directions() -> None:
    from hypervector.strategies.impulse_1m import register_impulse_1m

    clear_registry()
    try:
        register_impulse_1m()
        df = fixture_ohlcv(n_bars=1_500, drift=-4.0, wave_period=45)
        for name, grid in (
            ("impulse_1m_long", {"long_ema": [-15.0], "long_di": [-20.0], "long_roc": [-0.10]}),
            ("impulse_1m_short", {"short_ema": [15.0], "short_di": [15.0], "short_roc": [0.10]}),
        ):
            results = run_grid_search(df, get_strategy(name), param_grid=grid, cost=ZERO_COST)
            assert [r.status for r in results] == ["ok"], [r.error for r in results]
    finally:
        clear_registry()


def test_trial_metrics_still_rejects_unknown_directions() -> None:
    close = pd.Series(np.linspace(100.0, 101.0, 20))
    flags = pd.Series(False, index=close.index)
    with pytest.raises(ValueError, match="direction"):
        compute_trial_metrics(close, flags, flags, direction="sideways", cost=ZERO_COST)
