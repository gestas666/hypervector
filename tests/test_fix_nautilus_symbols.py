"""Nautilus runs build the instrument for the export symbol (not always BTC-PERP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.nautilus.config_stub import (
    build_phase2_stub_config,
    phase2_check_report,
)
from hypervector.nautilus.errors import UnsupportedNautilusSymbol
from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.nautilus.venue_spec import resolve_venue_spec
from nautilus_fix_support import capture_engine, synth_ohlcv, write_export


@pytest.mark.parametrize(
    ("symbol", "base", "decimals", "price_inc", "size_inc", "max_lev"),
    [
        ("ETH", 3_000.0, 2, "0.01", "0.0001", 25.0),
        ("SOL", 150.0, 3, "0.0001", "0.01", 20.0),
        ("HYPE", 30.0, 4, "0.0001", "0.01", 10.0),
    ],
)
def test_non_btc_export_runs_on_its_own_instrument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    base: float,
    decimals: int,
    price_inc: str,
    size_inc: str,
    max_lev: float,
) -> None:
    export_dir = write_export(tmp_path, symbol=symbol)
    captured = capture_engine(monkeypatch)
    df = synth_ohlcv(300, base=base, decimals=decimals)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )

    summary = json.loads(result.report_path.read_text())
    assert summary["instrument_id"] == f"{symbol}-PERP.HYPERLIQUID"
    assert summary["bar_type"].startswith(f"{symbol}-PERP.HYPERLIQUID-15-MINUTE")
    inst = summary["instrument"]
    assert inst["price_increment"] == price_inc
    assert inst["size_increment"] == size_inc
    assert inst["venue_max_leverage"] == max_lev
    assert inst["source"] == "builtin_venue_spec"
    assert summary["margin"]["margin_maint"] == pytest.approx(0.5 / max_lev)
    assert result.orders_count > 0
    instrument = captured["instrument"]
    assert str(instrument.id) == f"{symbol}-PERP.HYPERLIQUID"
    assert instrument.base_currency.code == symbol
    # Fills happen at the asset's own prices, not BTC's.
    assert all(abs(f["avg_px"] / base - 1.0) < 0.5 for f in captured["fills"])


def test_unknown_symbol_is_refused_before_history_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = write_export(tmp_path, symbol="DOGE")

    def _no_history(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("history must not load for an unsupported symbol")

    monkeypatch.setattr(
        "hypervector.nautilus.runner.load_research_history", _no_history
    )
    with pytest.raises(UnsupportedNautilusSymbol, match="DOGE"):
        run_phase2_backtest(export_dir=export_dir, data_root=tmp_path / "data")


def test_export_cached_venue_meta_enables_any_perp(tmp_path: Path) -> None:
    export_dir = write_export(
        tmp_path,
        symbol="DOGE",
        extra_meta={"instrument": {"name": "DOGE", "szDecimals": 0, "maxLeverage": 10}},
    )
    df = synth_ohlcv(300, base=0.2, decimals=5, vol=0.004)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["instrument_id"] == "DOGE-PERP.HYPERLIQUID"
    assert summary["instrument"]["source"] == "export_meta"
    assert summary["instrument"]["price_decimals"] == 6
    assert summary["instrument"]["size_increment"] == "1"
    assert summary["instrument"]["venue_max_leverage"] == 10.0


def test_charter_caps_cached_leverage() -> None:
    eth = resolve_venue_spec(
        "ETH", {"instrument": {"szDecimals": 4, "maxLeverage": 50}}
    )
    assert eth.venue_max_leverage == 25.0 and eth.leverage_capped_by_charter
    alt = resolve_venue_spec(
        "WIF", {"venue_meta": {"szDecimals": 0, "maxLeverage": 20}}
    )
    assert alt.venue_max_leverage == 15.0 and alt.leverage_capped_by_charter
    btc = resolve_venue_spec("BTC")
    assert btc.venue_max_leverage == 40.0 and btc.source == "builtin_btc_stub"
    with pytest.raises(UnsupportedNautilusSymbol, match="not 'ETH'"):
        resolve_venue_spec(
            "ETH", {"instrument": {"name": "SOL", "szDecimals": 2, "maxLeverage": 20}}
        )
    with pytest.raises(UnsupportedNautilusSymbol, match="szDecimals"):
        resolve_venue_spec("DOGE", {"instrument": {"maxLeverage": 10}})


def test_check_predicts_run_support(tmp_path: Path) -> None:
    eth = write_export(tmp_path / "eth", symbol="ETH")
    stub = build_phase2_stub_config(eth, data_root=tmp_path / "data")
    assert stub.instrument_id_hint == "ETH-PERP.HYPERLIQUID"
    report = phase2_check_report(eth, data_root=tmp_path / "data", probe_nautilus=False)
    assert report["ok"] is True and report["nautilus_run_supported"] is True

    doge = write_export(tmp_path / "doge", symbol="DOGE")
    report = phase2_check_report(
        doge, data_root=tmp_path / "data", probe_nautilus=False
    )
    assert report["ok"] is False
    assert report["nautilus_run_supported"] is False
    assert "DOGE" in report["unsupported_reason"]


def test_cli_run_unsupported_symbol_is_clean_json_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export_dir = write_export(tmp_path, symbol="DOGE")
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "nautilus",
            "run",
            "--export",
            str(export_dir),
            "--no-network",
        ]
    )
    captured = capsys.readouterr()
    # Refused before the engine loads (exit 2, a refusal), as error JSON.
    assert rc == 2
    err = json.loads(captured.err.strip().splitlines()[-1])
    assert err["ok"] is False
    assert err["error_type"] == "UnsupportedNautilusSymbol"
    assert err["symbol"] == "DOGE"
    assert "Traceback" not in captured.err
