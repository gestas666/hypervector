"""Autotune boards are reproducible on their own, and the API matches the CLI.

Regression tests:
- trial boards lacked data window, seed, requested sampler, cost model, search
  space and code identity; regime autotune had no durable board by default;
- '--sampler hybrid' was Optuna TPE recorded without the requested name;
- run_autotune defaulted to 5m/180d/CWD while the CLI uses 1m/90d/--data-root.
"""

from __future__ import annotations

from importlib.resources import files
import inspect
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.regime import tuning
from hypervector.sweep import autotune
from hypervector.sweep.autotune_models import SEARCH_SEED
from hypervector.sweep.costs import resolve_cost_model


def _stub(monkeypatch: pytest.MonkeyPatch, bars: pd.DataFrame) -> None:
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: (bars, {"sources": {"fixture": len(bars)}}),
    )
    monkeypatch.setattr(
        autotune,
        "compute_trial_metrics",
        lambda close, *_a, **_k: {
            "trade_count": 2,
            "sharpe": 0.1,
            "net_pnl": float(len(close)),
            "total_return_pct": 0.0,
            "max_drawdown": -0.01,
        },
    )


def test_board_carries_reproduction_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = fixture_ohlcv(n_bars=200, drift=1.0)
    _stub(monkeypatch, bars)

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="ma_cross_long",
        n_trials=4,
        fee_model="hl_vip1_taker",
        train_fraction=0.75,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    assert board["schema"] == "autotune_board/v2"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d.*", board["created_utc"])
    assert board["seed"] == SEARCH_SEED
    assert board["sampler_requested"] == "karpathy"
    assert board["sampler_used"] == "karpathy_random_adaptive"
    assert board["n_trials_requested"] == 4
    assert board["objective"] == "net_pnl"
    assert board["train_fraction"] == 0.75
    assert board["strict_hl_only"] is False
    assert board["force_refresh"] is False
    assert board["book_data_path"] is None
    assert board["data_provenance"] == {"sources": {"fixture": 200}}
    window = board["data_window"]
    assert window["bar_count"] == 200
    assert window["first_bar_utc"].startswith("2024-01-01T00:00:00")
    assert window["last_bar_utc"].startswith("2024-01-01T03:19:00")
    assert board["train_window"]["last_bar_utc"].startswith("2024-01-01T02:29:00")
    assert board["holdout_window"]["first_bar_utc"].startswith("2024-01-01T02:30:00")
    assert board["costs"] == resolve_cost_model("hl_vip1_taker").to_dict()
    assert board["search_space"]["param_grid"] == {"fast": [5, 10], "slow": [20, 30]}
    assert board["search_space"]["exit_space"]["mode"] == ["atr", "trail", "fixed_rr"]
    identity = board["code_identity"]
    assert re.fullmatch(r"[0-9a-f]{64}", identity["source_tree_sha256"])
    assert identity["git_commit"] is None or re.fullmatch(
        r"[0-9a-f]{40}", identity["git_commit"]
    )


def test_hybrid_is_an_explicit_alias_recorded_as_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, fixture_ohlcv(n_bars=150, drift=1.0))

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="ma_cross_long",
        sampler="hybrid",
        n_trials=2,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    assert board["sampler_requested"] == "hybrid"
    assert board["sampler_used"] == "optuna_tpe"
    assert result.sampler_used == "optuna_tpe"
    assert any("hybrid" in warning and "alias" in warning for warning in result.warnings)


def _spec(*parts: str) -> dict[str, object]:
    resource = files("hypervector.commands").joinpath("specs", *parts)
    return json.loads(resource.read_text(encoding="utf-8"))


def _defaults(spec: dict[str, object]) -> dict[str, object]:
    return {
        argument["options"]["dest"]: argument["options"].get("default")
        for argument in spec["arguments"]  # type: ignore[index, union-attr]
    }


def test_api_defaults_match_the_cli_spec() -> None:
    cli = {
        **_defaults(_spec("_fragments", "market.json")),
        **_defaults(_spec("_fragments", "fees.json")),
        **_defaults(_spec("tune", "strategy.json")),
    }
    api = {
        name: parameter.default
        for name, parameter in inspect.signature(autotune.run_autotune).parameters.items()
    }
    assert api["symbol"] == cli["symbol"]
    assert api["timeframe"] == cli["timeframe"]
    assert api["lookback_days"] == cli["lookback"]
    assert api["fee_model"] == cli["fee_model"]
    assert api["strategy_name"] == cli["strategy"]
    assert api["n_trials"] == cli["n_trials"]
    assert api["sampler"] == cli["sampler"]
    assert api["strict_hl_only"] == cli["strict_hl_only"]
    assert api["force_refresh"] == cli["force"]


def test_data_root_is_required_and_unambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read without an explicit data root"),
    )
    with pytest.raises(ValueError, match="data_root is required"):
        autotune.run_autotune()
    with pytest.raises(ValueError, match="disagree"):
        autotune.run_autotune(tmp_path / "a", data_root=tmp_path / "b")
    assert not (tmp_path / "logs").exists()


def _regime_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-01-01", periods=300, freq="1min", tz="UTC")
    close = np.concatenate([np.linspace(100.0, 105.0, 150), np.linspace(105.0, 99.0, 150)])
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
        },
        index=index,
    )
    positions = pd.DataFrame(
        {
            "open_time_utc": [index[100], index[140], index[250]],
            "side": ["long", "long", "short"],
            "symbol": ["BTC"] * 3,
        }
    )
    return bars, positions


def test_regime_tuning_board_is_durable_and_exclusive(tmp_path: Path) -> None:
    bars, positions = _regime_inputs()
    candidates = tuning.generate_candidate_parameters(n_trials=2, seed=11)
    board = tuning.autotune_regime_candidates(
        bars, positions, candidates, train_fraction=2.0 / 3.0, forward_horizon=5
    )
    document = tuning.regime_tuning_document(
        board,
        bars=bars,
        data_provenance={"source": "fixture"},
        seed=11,
        n_trials=2,
        train_fraction=2.0 / 3.0,
        forward_horizon=5,
        target_price_fraction=0.002,
    )

    first = tuning.publish_regime_tuning_board(document, tmp_path / "logs" / "research")
    second = tuning.publish_regime_tuning_board(document, tmp_path / "logs" / "research")

    assert first != second
    assert first.parent == second.parent == tmp_path / "logs" / "research"
    saved = json.loads(first.read_text())
    assert saved["schema"] == "regime_tuning_board/v1"
    assert saved["report_only"] is True
    assert saved["seed"] == 11
    assert saved["n_trials_requested"] == 2
    assert saved["train_fraction"] == pytest.approx(2.0 / 3.0)
    assert saved["data_provenance"] == {"source": "fixture"}
    assert saved["data_window"]["bar_count"] == 300
    assert re.fullmatch(r"[0-9a-f]{64}", saved["code_identity"]["source_tree_sha256"])
    assert saved["tuning_board"]["selection_basis"] == "train_only"
    fixed = tuning.publish_regime_tuning_board(document, tmp_path / "x", name="fixed.json")
    assert fixed == tmp_path / "x" / "fixed.json"
    with pytest.raises(FileExistsError):
        tuning.publish_regime_tuning_board(document, tmp_path / "x", name="fixed.json")
