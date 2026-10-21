"""Tests for Optuna/Karpathy autotuning module."""

import json
from pathlib import Path

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.schema import validate_export_dir
from hypervector.sweep import autotune
from hypervector.sweep.autotune import run_optuna_autotune
from synthetic_strategies import MANAGED_LONG


class _DeterministicRng:
    """Minimal RNG stub that selects the final value and maximum mutation."""

    def integers(self, _low: int, high: int) -> int:
        return high - 1

    def uniform(self, _low: float, high: float) -> float:
        return high


def test_grid_sampling_preserves_native_types_and_mutation_bounds():
    """Karpathy sampling must not stringify bools or exceed declared bounds."""
    rng = _DeterministicRng()
    grid = {"period": [9, 21], "enabled": [True, False], "leverage": [20.0, 40.0]}

    sampled = autotune._sample_grid_params(rng, grid)
    mutated = autotune._mutate_grid_params(rng, sampled, grid)

    assert sampled == {"period": 21, "enabled": False, "leverage": 40.0}
    assert type(sampled["period"]) is int
    assert type(sampled["enabled"]) is bool
    assert mutated["leverage"] == 40.0


def test_autotune_exports_strict_bundle(tmp_path: Path, monkeypatch):
    """The winner must use the repository's real strict export implementation.

    The managed synthetic strategy declares every execution option, so the
    bundle carries its fixed sizing, strategy-managed exits and maker fees.
    """
    bars = fixture_ohlcv(n_bars=180, drift=1.0)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_args, **_kwargs: (bars, {"sources": {"fixture": len(bars)}}),
    )

    result = run_optuna_autotune(
        strategy_name=MANAGED_LONG,
        symbol="BTC",
        timeframe="1m",
        lookback_days=30,
        n_trials=1,
        data_root=tmp_path,
        export_best=True,
        sampler="karpathy",
    )

    assert result.export_dir is not None
    assert validate_export_dir(result.export_dir, strict=True)["ok"] is True
    params = json.loads((result.export_dir / "params.json").read_text())
    assert params["strategy"] == MANAGED_LONG
    assert params["exit_mode"] == "strategy_managed"
    assert result.best_exit_cfg == {"mode": "strategy_managed", "stop": None, "leverage": 10.0}
    meta = json.loads((result.export_dir / "meta.json").read_text())
    assert meta["risk"]["risk_pct_min"] == 0.5
    assert meta["risk"]["risk_pct_max"] == 0.5
    assert meta["risk"]["max_size_frac"] == 5.0
    assert meta["exits"] == {"mode": "strategy_managed", "stop": None, "leverage": 10.0}
    assert meta["execution_profile"]["post_only_entries"] is True
    assert meta["costs"]["taker_fee"] == 0.00015
    assert meta["costs"]["slippage_bps"] == 0.0
    board = json.loads(result.board_path.read_text())
    assert board["fee_model"] == "hl_maker"
    assert board["search_space"]["execution_profile"]["fixed_margin_fraction"] == 0.5
    assert all(
        trial["exit_cfg"]["mode"] == "strategy_managed"
        for trial in board["all_trials"]
    )


def test_autotune_smoke(tmp_path: Path, monkeypatch):
    # Run a fast autotune smoke test with n_trials=3
    bars = fixture_ohlcv(n_bars=180, drift=1.0)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_args, **_kwargs: (bars, {"sources": {"fixture": len(bars)}}),
    )
    res = run_optuna_autotune(
        strategy_name="test_sma_cross_long",
        symbol="BTC",
        timeframe="5m",
        lookback_days=180,
        n_trials=3,
        data_root=tmp_path,
        export_best=False,
    )
    assert res.strategy_name == "test_sma_cross_long"
    assert res.n_trials == 3
    assert set(res.best_params) == {"fast", "slow"}
    assert res.board_path.is_file()
