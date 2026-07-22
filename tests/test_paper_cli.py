"""Paper CLI: paper-check identity + paper-run daemon offline path."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.paper.runner import PaperDaemonResult, start_paper_daemon


def _write_strict_export(root: Path, *, strategy: str = "crown_stack_short") -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="papercli1",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": track,
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
            "data_provenance": {"sources": {"fixture": 100}},
        },
        params={
            "strategy": strategy,
            "bbwp_lookback": 100,
            "bbwp_threshold": 20.0,
            "exit_mode": "fixed_rr",
            "role": track,
        },
        metrics={
            "net_pnl": 50.0,
            "total_return_pct": 0.5,
            "sharpe": 0.4,
            "trade_count": 3,
        },
        candidate_id="paper_cli_crown",
        strict=True,
    )


def test_paper_check_reports_mode(tmp_path: Path, capsys, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(data), "paper-check"])
    assert rc == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["paper"]["execution_mode"] == "paper"
    assert report["paper"]["live_feed_loop"] is True
    assert report["paper"]["sandbox_enabled"] is False
    assert report["paper"]["secrets_present"] is False
    assert "decisions" in report["paper"]
    assert "ledger" in report["paper"]
    # Env *names* may be listed; never print secret *values* (none set here).
    assert "secret_env_names" in report["paper"]


def test_paper_check_secrets_present_true(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    rc = main(["--data-root", str(tmp_path / "data"), "paper-check"])
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["paper"]["secrets_present"] is True
    assert "sekrit" not in out
    assert "0xabc" not in out


def test_paper_run_requires_export_path():
    with pytest.raises(SystemExit) as exc:
        main(["paper-run"])
    assert exc.value.code != 0


def test_paper_run_help():
    with pytest.raises(SystemExit) as exc:
        main(["paper-run", "--help"])
    assert exc.value.code == 0


def test_start_paper_daemon_offline_injected_bars(tmp_path: Path, capsys):
    """Daemon warm-up + live poll mock; no network; stop after max live bars."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=50, drift=-5.0, wave_period=20)
    live = fixture_ohlcv(n_bars=10, drift=-5.0, wave_period=20)
    # Shift live timestamps after warm so they count as new bars
    live = live.copy()
    live["timestamp"] = warm["timestamp"].iloc[-1] + (
        live["timestamp"] - live["timestamp"].iloc[0]
    ) + (warm["timestamp"].iloc[1] - warm["timestamp"].iloc[0])

    calls = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return live
        return live.iloc[0:0].copy()  # empty thereafter

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        conviction=0.5,
        fee_tier=0,
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        max_live_bars=10,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert isinstance(result, PaperDaemonResult)
    assert result.warm_bars == 50
    assert result.live_bars == 10
    assert result.bars_processed == 60
    assert result.decisions_path.is_file()
    assert result.stop_reason in ("max_live_bars", "poll_exhausted", "stop")
    text = result.decisions_path.read_text(encoding="utf-8")
    assert "execution_mode" in text
    assert "paper" in text
    # Banner on stderr
    err = capsys.readouterr().err
    assert "PAPER MODE" in err
    assert "no venue orders" in err.lower() or "no venue" in err.lower()


def test_start_paper_daemon_stop_file(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=5, drift=-1.0)
    stop = tmp_path / "STOP"
    poll_count = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        poll_count["n"] += 1
        if poll_count["n"] >= 2:
            stop.write_text("stop", encoding="utf-8")
        return warm.iloc[0:0].copy()

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        stop_file=stop,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert result.stop_reason == "stop_file"
    assert result.warm_bars == 5


def test_cli_paper_run_offline_via_monkeypatch(tmp_path: Path, capsys, monkeypatch):
    """CLI paper-run calls daemon; inject offline path so no network."""
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    warm = fixture_ohlcv(n_bars=20, drift=-3.0, wave_period=15)

    def fake_daemon(**kwargs):
        return start_paper_daemon(
            export_dir=kwargs["export_dir"],
            data_root=kwargs["data_root"],
            conviction=kwargs.get("conviction", 0.5),
            fee_tier=kwargs.get("fee_tier", 0),
            sandbox_enabled=kwargs.get("sandbox_enabled", False),
            stop_file=kwargs.get("stop_file"),
            warm_ohlcv=warm,
            poll_fn=lambda **_: warm.iloc[0:0].copy(),
            max_live_bars=0,
            poll_interval_secs=0.0,
            sleep_fn=lambda _s: None,
            install_signal_handlers=False,
        )

    monkeypatch.setattr("hypervector.cli.start_paper_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(data),
            "paper-run",
            "--path",
            str(export),
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert "PAPER MODE" in out.err
    payload = json.loads(out.out)
    assert payload["ok"] is True
    assert payload["execution_mode"] == "paper"
    assert payload["warm_bars"] == 20
