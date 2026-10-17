"""A Hypervelocity autotune bundle must say what was measured.

Regression test: the export wrote ``exits = {mode: fixed_rr, sl_pct: target,
rr: 1.0}`` (a symmetric stop at the target) and metrics said ``exit_mode: atr``,
next to a contract saying ``stop: null`` and a run measured with
strategy-managed exits only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import ExportSchemaError, validate_export_dir
from hypervector.strategies.hypervelocity_contract import HypervelocityContract
from hypervector.sweep import autotune


def test_hypervelocity_bundle_matches_the_measured_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = fixture_ohlcv(n_bars=180, drift=1.0)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: (bars, {"sources": {"fixture": len(bars)}}),
    )

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name="hypervelocity_1m_scalper_long",
        n_trials=1,
        train_fraction=1.0,
    )

    assert result.export_dir is not None
    report = validate_export_dir(result.export_dir, strict=True)
    meta = report["meta"]
    contract = HypervelocityContract()
    assert meta["tp_sl_mode"] == "strategy_target_only"
    assert meta["exits"]["mode"] == "strategy_target_only"
    assert meta["exits"]["stop"] is None
    assert meta["exits"]["target_price_fraction"] == contract.target_price_fraction
    assert "sl_pct" not in meta["exits"]
    assert meta["exits"] == meta["hypervelocity_contract"]
    assert report["params"]["exit_mode"] == "strategy_target_only"
    assert report["metrics"]["exit_mode"] == "strategy_target_only"
    assert result.best_metrics["exit_mode"] == "strategy_target_only"
    board = json.loads(result.board_path.read_text())
    assert board["all_trials"][0]["metrics"]["exit_mode"] == "strategy_target_only"
    # The risk contract is unchanged.
    assert meta["risk"]["max_size_frac"] == contract.notional_fraction
    # Downstream consumers still load the bundle; Nautilus keeps strategy exits.
    from hypervector.nautilus.actor import _uses_strategy_exits_only, config_from_loadout
    from hypervector.nautilus.load_export import load_strategy_loadout

    loadout = load_strategy_loadout(result.export_dir, strict=True)
    assert loadout.exit_mode == "strategy_target_only"
    config = config_from_loadout(
        loadout, bar_type="BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL"
    )
    assert config.exits["mode"] == "strategy_target_only"
    assert config.exits["stop"] is None
    assert _uses_strategy_exits_only(config.strategy_name)


def _bundle(tmp_path: Path, strategy: str, exits: dict[str, object]) -> Path:
    return export_candidate(
        tmp_path / "exports",
        run_id="r1",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "init_cash": 10_000.0,
            "tp_sl_mode": exits["mode"],
            "exits": exits,
            "risk": {"risk_pct_min": 0.7, "risk_pct_max": 0.7, "max_size_frac": 21.0},
            "costs": {"taker_fee": 0.00015, "slippage_bps": 0.0},
        },
        params={"strategy": strategy},
        metrics={},
        candidate_id=f"{strategy}_{len(list((tmp_path).rglob('meta.json')))}",
        validate=False,
    )


def _target_exits(**overrides: object) -> dict[str, object]:
    exits: dict[str, object] = dict(autotune._hypervelocity_exit_dict())
    exits.update(overrides)
    return exits


def test_strategy_target_only_is_strict_valid_for_hypervelocity(tmp_path: Path) -> None:
    path = _bundle(tmp_path, "hypervelocity_1m_scalper_long", _target_exits())
    assert validate_export_dir(path, strict=True)["tp_sl_mode"] == "strategy_target_only"


@pytest.mark.parametrize(
    ("strategy", "exits", "message"),
    [
        ("ma_cross_long", _target_exits(), "Hypervelocity"),
        ("hypervelocity_1m_scalper_long", _target_exits(stop=0.002), "stop"),
        (
            "hypervelocity_1m_scalper_long",
            _target_exits(target_price_fraction=0.0),
            "target_price_fraction",
        ),
        (
            "hypervelocity_1m_scalper_long",
            _target_exits(target_price_fraction="x"),
            "target_price_fraction",
        ),
    ],
)
def test_strategy_target_only_fails_closed_elsewhere(
    tmp_path: Path, strategy: str, exits: dict[str, object], message: str
) -> None:
    path = _bundle(tmp_path, strategy, exits)
    with pytest.raises(ExportSchemaError, match=message):
        validate_export_dir(path, strict=True)
