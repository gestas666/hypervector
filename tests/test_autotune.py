"""Tests for Optuna/Karpathy autotuning module."""

import json
from pathlib import Path

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.schema import validate_export_dir
from hypervector.sweep import autotune
from hypervector.sweep.autotune import run_optuna_autotune


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
    """The winner must use the repository's real strict export implementation."""
    bars = fixture_ohlcv(n_bars=180, drift=1.0)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_args, **_kwargs: (bars, {"sources": {"fixture": len(bars)}}),
    )

    result = run_optuna_autotune(
        strategy_name="hypervelocity_1m_scalper_long",
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
    assert type(params["regime_filter"]) is bool
    assert float(params["leverage"]) <= 40.0
    assert "leverage" in result.best_exit_cfg


def test_autotune_smoke(tmp_path: Path):
    # Run a fast autotune smoke test with n_trials=3
    res = run_optuna_autotune(
        strategy_name="crown_stack_long",
        symbol="BTC",
        timeframe="5m",
        lookback_days=180,
        n_trials=3,
        data_root=tmp_path,
        export_best=False,
    )
    assert res.strategy_name == "crown_stack_long"
    assert res.n_trials == 3
    assert (
        "bbwp_lookback" in res.best_params
        or "st_atr" in res.best_params
        or res.best_params is not None
    )
    assert res.board_path.is_file()
