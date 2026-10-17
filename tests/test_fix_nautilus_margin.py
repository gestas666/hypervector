"""Sim margin follows the configured leverage (capped by venue max), honestly reported."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

import hypervector.nautilus.runner as runner_mod
from hypervector.data.sources import fixture_ohlcv
from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import capture_engine, synth_ohlcv, write_export


def _summary(result) -> dict:
    return json.loads(result.report_path.read_text())


def test_ordinary_strategy_margin_is_one_x(tmp_path: Path, monkeypatch) -> None:
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=write_export(tmp_path),
        data_root=tmp_path / "data",
        ohlcv=synth_ohlcv(200),
    )
    margin = _summary(result)["margin"]
    assert margin["sim_leverage"] == 1.0
    assert margin["margin_init"] == pytest.approx(1.0)  # was 0.025 (= 40x)
    assert margin["margin_maint"] == pytest.approx(0.0125)  # BTC: 0.5 / 40
    assert margin["venue_max_leverage"] == 40.0
    assert margin["margin_model"] == "standard_init_1_over_sim_leverage"
    assert float(captured["instrument"].margin_init) == pytest.approx(1.0)
    assert "native_liquidation" in _summary(result)["event_venue_model_gaps"]


@pytest.mark.parametrize(("symbol", "expected"), [("BTC", 30.0), ("ETH", 25.0)])
def test_hypervelocity_leverage_capped_by_venue_max(
    tmp_path: Path, symbol: str, expected: float
) -> None:
    export_dir = write_export(
        tmp_path, strategy="hypervelocity_1m_scalper", timeframe="1m", symbol=symbol
    )
    base = 40_000.0 if symbol == "BTC" else 3_000.0
    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=tmp_path / "data",
        ohlcv=fixture_ohlcv(n_bars=80, drift=2.0, wave_period=20, base_price=base),
    )
    margin = _summary(result)["margin"]
    assert margin["sim_leverage"] == expected
    assert margin["margin_init"] == pytest.approx(1.0 / expected)


def test_margin_model_change_does_not_change_fills(tmp_path: Path, monkeypatch) -> None:
    """Margin is reported, not enforced: no new denial/liquidation gate."""
    export_dir = write_export(tmp_path)
    df = synth_ohlcv(400)
    captured = capture_engine(monkeypatch)
    new = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "d1", ohlcv=df
    )
    new_fills = list(captured["fills"])

    # Legacy configuration: LeveragedMarginModel with the 2.5% stub margin.
    from nautilus_trader.backtest.models import LeveragedMarginModel

    original_build = runner_mod.perp_instrument_from_spec

    def _legacy_build(spec, **kw):
        kw["margin_init"] = Decimal("0.025")
        return original_build(spec, **kw)

    monkeypatch.setattr(runner_mod, "perp_instrument_from_spec", _legacy_build)
    monkeypatch.setattr(runner_mod, "StandardMarginModel", LeveragedMarginModel)
    captured2 = capture_engine(monkeypatch)
    old = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "d2", ohlcv=df
    )
    old_fills = captured2["fills"]

    strip = lambda fills: [  # noqa: E731
        (f["side"], f["ts_last"], f["filled_qty"], f["avg_px"]) for f in fills
    ]
    assert strip(new_fills) == strip(old_fills)
    assert new.pnl == pytest.approx(old.pnl)
    assert new.orders_count == old.orders_count
