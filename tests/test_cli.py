"""CLI entry points — drive real handlers; live fetchers injected for speed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.data.oxa_history import DEFAULT_BOOK_MAX_PAGES, OxaBookRequest
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

        monkeypatch.setattr("hypervector.data.pipeline.load_research_history", fake_load)
        monkeypatch.setattr(
            "hypervector.data.pipeline.load_research_history", fake_load
        )
        # Runner binds load_research_history at import; patch for nautilus run E2E.
        monkeypatch.setattr(
            "hypervector.nautilus.runner.load_research_history", fake_load
        )
        return df, prov

    return _install


def test_cli_history_twice_cache(tmp_path: Path, capsys, inject_history):
    inject_history()
    data = tmp_path / "data"
    argv = [
        "--data-root",
        str(data),
        "data",
        "history",
        "--lookback-days",
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


def test_cli_regime_classify(tmp_path: Path, capsys, inject_history):
    inject_history()
    data = tmp_path / "data"
    rc = main(
        [
            "--data-root",
            str(data),
            "regime",
            "classify",
            "--detector",
            "ema",
            "--lookback-days",
            "30",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["detector"] == "ema"
    assert "metrics" in payload
    assert "data_provenance" in payload
    assert not (data / "exports").exists() or not any((data / "exports").iterdir())


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
    sweep = ["--data-root", str(data), "backtest", "sweep", "--lookback-days", "30"]
    up = ["--track", "uptrend", "--strategy", "test_sma_cross_long"]
    assert main([*sweep, *up]) == 0
    up_out = capsys.readouterr().out
    assert "net_pnl" in up_out

    down = ["--track", "downtrend", "--strategy", "test_sma_cross_short"]
    assert main([*sweep, *down]) == 0
    assert (data / "runs" / "hypervector.db").is_file()
    report = ["--data-root", str(data), "backtest", "report", "--track", "uptrend"]
    assert main(report) == 0


def test_cli_rejects_lookback_below_floor(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(tmp_path), "data", "history", "--lookback-days", "10"])
    assert exc.value.code == 2


def test_cli_oxa_book_fetch_is_bounded_and_secret_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acquisition CLI fixes venue and keeps credentials out of output."""
    captured: dict[str, object] = {}
    secret = "configured-test-secret"

    def fake_acquire(
        *, data_root: Path | str, api_key: str, request: OxaBookRequest
    ) -> dict[str, object]:
        captured.update(data_root=data_root, api_key=api_key, request=request)
        return {
            "ok": True,
            "directory": str(tmp_path / "evidence"),
            "books_path": str(tmp_path / "evidence" / "books.jsonl"),
            "request_ids": ["request-1"],
            "row_count": 1,
            "complete": False,
            "continuation_cursor": "more",
        }

    monkeypatch.setenv("OXA_API_KEY", secret)
    monkeypatch.setattr(
        "hypervector.data.oxa_history.acquire_and_store_orderbooks", fake_acquire
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "archive",
            "book-fetch",
            "--symbol",
            "BTC",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(output)
    request = captured["request"]
    assert rc == 0
    assert captured["api_key"] == secret
    assert request.limit == 1000
    assert request.max_pages == DEFAULT_BOOK_MAX_PAGES
    assert request.depth == 20
    assert report["venue"] == "hyperliquid"
    assert secret not in output


def test_cli_oxa_book_fetch_reports_technical_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vendor failure returns non-success with no fabricated acquisition."""
    from hypervector.data.oxa_history import OxaHistoryError

    def fail_acquire(
        *, data_root: Path | str, api_key: str, request: OxaBookRequest
    ) -> dict[str, object]:
        raise OxaHistoryError("0xArchive request failed with HTTP 503")

    monkeypatch.setenv("OXA_API_KEY", "configured-test-secret")
    monkeypatch.setattr(
        "hypervector.data.oxa_history.acquire_and_store_orderbooks", fail_acquire
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "archive",
            "book-fetch",
            "--symbol",
            "BTC",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert rc == 1
    assert captured.out == ""
    assert report["ok"] is False
    assert report["error"] == "0xArchive request failed with HTTP 503"
    assert "books_path" not in report


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
                "backtest",
                "sweep",
                "--track",
                "downtrend",
                "--lookback-days",
                "30",
                "--strategy",
                "test_sma_cross_short",
                "--initial-cash",
                "10000",
                "--exit-mode",
                "atr",
                "--risk-min",
                "0.01",
                "--risk-max",
                "0.05",
                "--conviction",
                "0.5",
            ]
        )
        == 0
    )
    capsys.readouterr()
    exports = list((data / "exports").iterdir())
    assert exports, "backtest sweep should write a bundle by default"
    export_path = exports[0]

    assert (
        main(
            [
                "--data-root",
                str(data),
                "export",
                "validate",
                "--export",
                str(export_path),
            ]
        )
        == 0
    )
    val = json.loads(capsys.readouterr().out)
    assert val["ok"] is True
    assert val["strategy"] == "test_sma_cross_short"
    assert val["has_costs"] is True
    assert val["has_exits"] is True

    assert (
        main(
            [
                "--data-root",
                str(data),
                "nautilus",
                "check",
                "--export",
                str(export_path),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["ok"] is True
    assert report["phase2_stub"]["loadout"]["strategy_name"] == "test_sma_cross_short"
    assert report["phase2_stub"]["exits"]["mode"] == "atr"
    assert report["paper_live"]["implemented"] is True
    assert report["paper_live"]["paper_dry_run"]["implemented"] is True
    assert report["paper_live"]["paper_dry_run"]["command"] == "paper run"
    assert report["paper_live"]["live_submit"]["implemented"] is True
    assert report["paper_live"]["live_submit"]["command"] == "live start"
    assert "'paper run'" in captured.err
    assert "'live start'" in captured.err

    # DB re-export should also be Phase 2-ready (research_meta path)
    assert (
        main(["--data-root", str(data), "export", "create", "--track", "downtrend"])
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    reexport_path = Path(created["export_dir"])
    assert created["artifacts"]["export"] == str(reexport_path)
    assert reexport_path.is_dir()
    assert (
        main(
            [
                "--data-root",
                str(data),
                "export",
                "validate",
                "--export",
                str(reexport_path),
            ]
        )
        == 0
    )


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
            "export",
            "validate",
            "--export",
            str(bad),
        ]
    )
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert err["errors"]


def test_cli_infra_init(tmp_path: Path, capsys):
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "system", "init"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dirs"]["exports"]["exists"] is True
    assert report["dirs"]["paper_ledger"]["exists"] is True
    assert report["rules"]["paper_live_separated"] is True


def _strict_export_for_phase2(exports_root: Path) -> Path:
    """Write a Phase 1.5 strict export suitable for nautilus run."""
    from hypervector.export.phase2 import export_candidate

    return export_candidate(
        exports_root,
        run_id="cli_p2",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": "uptrend",
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 200}},
        },
        params={
            "strategy": "test_sma_cross_long",
            "exit_mode": "fixed_rr",
            "fast": 5,
            "slow": 20,
        },
        metrics={
            "net_pnl": 100.0,
            "total_return_pct": 1.0,
            "sharpe": 0.5,
            "trade_count": 5,
        },
        candidate_id="cli_phase2_run",
        strict=True,
    )


def test_cli_phase2_run_offline(tmp_path: Path, capsys, inject_history):
    """nautilus run: strict export + injected OHLCV → JSON summary, artifacts."""
    from hypervector.data.sources import fixture_ohlcv

    # Short wave series: MA cross fires; keep engine time reasonable
    df = fixture_ohlcv(n_bars=200, drift=5.0, wave_period=40, source="hl")
    inject_history(df, summarize_provenance(df))

    data = tmp_path / "data"
    export_dir = _strict_export_for_phase2(data / "exports")

    rc = main(
        [
            "--data-root",
            str(data),
            "nautilus",
            "run",
            "--export",
            str(export_dir),
            "--lookback-days",
            "30",
            "--conviction",
            "0.5",
            "--no-network",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["ok"] is True
    assert summary["execution_mode"] == "phase2_historical"
    assert "orders_count" in summary
    assert isinstance(summary["orders_count"], int)
    assert "pnl" in summary
    assert "report_path" in summary
    assert Path(summary["report_path"]).is_file()
    assert summary["loadout"]["strategy_name"] == "test_sma_cross_long"
    # Historical only — do not claim paper/live ran
    assert "paper/live not implemented" not in captured.err
    assert "paper ran" not in captured.err.lower()
    # Artifacts under data/nautilus/backtest/
    assert (data / "nautilus" / "backtest").is_dir()
    assert any((data / "nautilus" / "backtest").rglob("summary.json"))


def test_cli_phase2_run_schema_error(tmp_path: Path, capsys):
    """nautilus run exits 1 on invalid export (ExportSchemaError)."""
    bad = tmp_path / "bad_export"
    bad.mkdir()
    (bad / "meta.json").write_text("{}", encoding="utf-8")
    (bad / "params.json").write_text("{}", encoding="utf-8")
    (bad / "metrics.json").write_text("{}", encoding="utf-8")

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "nautilus",
            "run",
            "--export",
            str(bad),
            "--lookback-days",
            "30",
        ]
    )
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert err["errors"]


@pytest.mark.parametrize("removed", ["--paper", "--live"])
def test_cli_nautilus_run_rejects_removed_mode_flags(tmp_path: Path, removed: str):
    """The old no-op mode flags are gone; an unknown flag is a usage error."""
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--data-root",
                str(tmp_path / "data"),
                "nautilus",
                "run",
                "--export",
                str(tmp_path),
                removed,
            ]
        )
    assert exc.value.code == 2


def test_cli_autotune_wires_current_runner_arguments(
    tmp_path: Path, capsys, monkeypatch
):
    """The CLI must use the current autotuner fee and path parameter names."""
    captured: dict = {}

    def fake_autotune(**kwargs):
        captured.update(kwargs)
        return type(
            "Result",
            (),
            {
                "strategy_name": kwargs["strategy_name"],
                "symbol": kwargs["symbol"],
                "timeframe": kwargs["timeframe"],
                "lookback_days": kwargs["lookback_days"],
                "n_trials": kwargs["n_trials"],
                "sampler_used": "optuna_tpe",
                "best_params": {},
                "best_exit_cfg": {},
                "best_metrics": {},
                "export_dir": None,
                "board_path": tmp_path / "board.json",
            },
        )()

    monkeypatch.setattr("hypervector.sweep.autotune.run_optuna_autotune", fake_autotune)
    data_root = tmp_path / "data"

    rc = main(
        [
            "--data-root",
            str(data_root),
            "tune",
            "strategy",
            "--strategy",
            "test_managed_long",
            "--timeframe",
            "1m",
            "--fee-model",
            "hl_vip1_taker",
            "--n-trials",
            "2",
            "--no-export",
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert captured["fee_model"] == "hl_vip1_taker"
    assert captured["data_root"] == data_root
