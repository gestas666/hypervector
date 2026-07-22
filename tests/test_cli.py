"""CLI entry points — drive real handlers; live fetchers injected for speed."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.sources import split_source_frames
from hypervector.data.history import merge_history
from hypervector.data.provenance import summarize_provenance


def _live_shaped_history(tmp_path: Path):
    """Multi-venue bars with real provenance labels (not product fixture path)."""
    frames = split_source_frames(hl_bars=80, binance_extra=40, bybit_extra=10)
    df = merge_history(
        frames["hl"],
        [("binance", frames["binance"]), ("bybit", frames["bybit"])],
    )
    return df, summarize_provenance(df)


@pytest.fixture
def inject_history(monkeypatch):
    def _install(df=None, prov=None):
        if df is None:
            df, prov = _live_shaped_history(Path("."))
        def fake_load(data_root, **kwargs):
            # still write cache as real pipeline would
            from hypervector.data.cache import ParquetCache
            from hypervector.data.pipeline import cache_key

            root = Path(data_root)
            cache = ParquetCache(root / "cache")
            key = cache_key(
                kwargs.get("symbol", "BTC"),
                kwargs.get("timeframe", "1m"),
                kwargs.get("lookback_days", 90),
            )
            if not kwargs.get("force_refresh") and cache.exists(key):
                loaded = cache.load(key)
                assert loaded is not None
                return loaded, summarize_provenance(loaded)
            cache.save(key, df)
            return df, prov if prov is not None else summarize_provenance(df)

        monkeypatch.setattr("hypervector.cli.load_research_history", fake_load)
        monkeypatch.setattr(
            "hypervector.data.pipeline.load_research_history", fake_load
        )
        return df, prov

    return _install


def test_cli_history_twice_cache(tmp_path: Path, capsys, inject_history):
    inject_history()
    data = tmp_path / "data"
    argv = [
        "--data-root",
        str(data),
        "history",
        "--lookback",
        "30",
        "--symbol",
        "BTC",
        "--timeframe",
        "1m",
    ]
    assert main(argv) == 0
    out1 = json.loads(capsys.readouterr().out)
    assert out1["bars"] > 0
    assert "provenance" in out1
    assert set(out1["provenance"]["sources"]).issubset({"hl", "binance", "bybit"})

    assert main(argv) == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["bars"] == out1["bars"]


def test_cli_regime_export(tmp_path: Path, capsys, inject_history):
    inject_history()
    data = tmp_path / "data"
    rc = main(
        [
            "--data-root",
            str(data),
            "regime",
            "--lookback",
            "30",
            "--export",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "metrics" in payload
    assert "data_provenance" in payload
    assert (data / "exports" / "regime_BTC" / "meta.json").is_file()


def test_cli_sweep_up_and_down(tmp_path: Path, capsys, inject_history):
    # Wavy multi-source frame for trades
    from hypervector.data.sources import fixture_ohlcv

    # Strategy math needs crosses; use synthetic series labeled as if from merge
    # but CLI still goes through load_research_history injection (not fixture flag).
    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30, source="hl")
    # stamp mix of sources for provenance honesty
    df = df.copy()
    df.loc[df.index[:50], "source"] = "binance"
    inject_history(df, summarize_provenance(df))

    data = tmp_path / "data"
    assert main(["--data-root", str(data), "sweep-up", "--lookback", "30", "--export"]) == 0
    up_out = capsys.readouterr().out
    assert "net_pnl" in up_out or "ma_cross" in up_out

    assert main(["--data-root", str(data), "sweep-down", "--lookback", "30", "--export"]) == 0
    assert (data / "runs" / "hypervector.db").is_file()
    assert main(["--data-root", str(data), "report", "--track", "uptrend"]) == 0


def test_cli_rejects_lookback_below_floor(tmp_path: Path):
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "history",
            "--lookback",
            "10",
        ]
    )
    assert rc == 2


def test_cli_export_validate_and_phase2_check(tmp_path: Path, capsys, inject_history):
    from hypervector.data.sources import fixture_ohlcv

    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30, source="hl")
    inject_history(df, summarize_provenance(df))
    data = tmp_path / "data"

    assert (
        main(
            [
                "--data-root",
                str(data),
                "sweep-down",
                "--lookback",
                "30",
                "--strategy",
                "crown_stack_short",
                "--cash",
                "10000",
                "--tp-sl-mode",
                "atr",
                "--risk-min",
                "0.01",
                "--risk-max",
                "0.05",
                "--conviction",
                "0.5",
                "--export",
            ]
        )
        == 0
    )
    capsys.readouterr()
    exports = list((data / "exports").iterdir())
    assert exports, "sweep --export should write a bundle"
    export_path = exports[0]

    assert (
        main(
            [
                "--data-root",
                str(data),
                "export-validate",
                "--path",
                str(export_path),
                "--strict",
            ]
        )
        == 0
    )
    val = json.loads(capsys.readouterr().out)
    assert val["ok"] is True
    assert val["strategy"] == "crown_stack_short"
    assert val["has_costs"] is True

    assert (
        main(
            [
                "--data-root",
                str(data),
                "phase2-check",
                "--path",
                str(export_path),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["ok"] is True
    assert report["phase2_stub"]["loadout"]["strategy_name"] == "crown_stack_short"
    assert report["paper_live"]["implemented"] is False
    assert "paper/live not implemented" in captured.err


def test_cli_export_validate_fails_on_garbage(tmp_path: Path, capsys):
    bad = tmp_path / "bad_export"
    bad.mkdir()
    (bad / "meta.json").write_text("{}", encoding="utf-8")
    (bad / "params.json").write_text("{}", encoding="utf-8")
    (bad / "metrics.json").write_text("{}", encoding="utf-8")
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "export-validate",
            "--path",
            str(bad),
        ]
    )
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert err["errors"]


def test_cli_infra_init(tmp_path: Path, capsys):
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "infra-init"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dirs"]["exports"]["exists"] is True
    assert report["dirs"]["paper_ledger"]["exists"] is True
    assert report["rules"]["paper_live_separated"] is True
