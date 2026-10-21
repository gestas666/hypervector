"""Stage glue: sweep/report/RunsDB, nautilus, paper, model, regime, live check, tune."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import hypervector
from hypervector.cli import main
from hypervector.data.provenance import summarize_provenance
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.runs.db import RunsDB, TrialRow

EXITS = {
    "mode": "fixed_rr",
    "sl_pct": 0.01,
    "rr": 2.0,
    "atr_length": 14,
    "sl_atr_mult": 1.5,
    "trail_atr_mult": 2.0,
}
WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SIGNING_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"


def _strict_export(
    data: Path,
    name: str = "cand",
    *,
    strategy: str = "test_sma_cross_short",
    lookback_days: int = 45,
    symbol: str = "BTC",
) -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        data / "exports",
        run_id=f"run-{name}",
        meta={
            "symbol": symbol,
            "timeframe": "1m",
            "track": track,
            "lookback_days": lookback_days,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": EXITS,
            "costs": {"taker_fee": 0.00045, "slippage_bps": 2.0},
            "risk": {"risk_pct_min": 0.01, "risk_pct_max": 0.05},
        },
        params={"strategy": strategy, "role": track},
        metrics={"net_pnl": -5.0, "trade_count": 2},
        candidate_id=name,
        strict=True,
    )


@pytest.fixture
def history(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Offline research history; records every load request."""
    calls: list[dict[str, object]] = []
    frame = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30, source="hl")

    def fake_load(data_root: object, **kwargs: object):
        calls.append({"data_root": data_root, **kwargs})
        return frame, summarize_provenance(frame)

    monkeypatch.setattr("hypervector.data.pipeline.load_research_history", fake_load)
    return calls


# --- RunsDB -----------------------------------------------------------------------


def _trial(pnl: float, **overrides: object) -> TrialRow:
    values: dict[str, object] = dict(
        run_id="r",
        track="uptrend",
        strategy="s",
        params={},
        net_pnl=pnl,
        total_return_pct=0.0,
        sharpe=0.0,
        trade_count=1,
        wins=0,
        losses=1,
        win_pct=0.0,
        max_drawdown=0.0,
    )
    values.update(overrides)
    return TrialRow(**values)  # type: ignore[arg-type]


def test_insert_trials_commits_once_and_rolls_back_as_a_unit(tmp_path: Path) -> None:
    database = RunsDB(tmp_path / "runs.db")
    statements: list[str] = []
    database._conn.set_trace_callback(statements.append)
    try:
        ids = database.insert_trials([_trial(1.0), _trial(2.0), _trial(3.0)])
        assert len(ids) == 3
        assert sum(s.strip().upper() == "COMMIT" for s in statements) == 1
        with pytest.raises(ValueError):
            database.insert_trials([_trial(4.0), _trial(5.0, net_pnl="not-a-number")])
        assert len(database.list_trials()) == 3
        assert database.insert_trial(_trial(6.0)) > 0
    finally:
        database.close()


# --- backtest sweep ---------------------------------------------------------------


def test_sweep_prints_json_and_exports_the_selected_trial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], history: list[dict[str, object]]
) -> None:
    data = tmp_path / "data"
    argv = ["--data-root", str(data), "backtest", "sweep", "--track", "uptrend"]
    assert main([*argv, "--strategy", "test_sma_cross_long", "--lookback-days", "30"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True and result["track"] == "uptrend"
    assert result["strategy"] == "test_sma_cross_long"
    assert result["trials"] == result["ok_trials"] + result["failed_trials"]
    assert result["artifacts"]["board"] == str(
        (data / "runs" / "hypervector.db").resolve()
    )
    export_dir = Path(result["artifacts"]["export"])
    assert export_dir.is_dir() and result["export_dir"] == str(export_dir)
    params = json.loads((export_dir / "params.json").read_text())
    assert params["strategy"] == "test_sma_cross_long"
    database = RunsDB(data / "runs" / "hypervector.db")
    try:
        rows = database.list_trials(run_id=result["run_id"])
    finally:
        database.close()
    assert len(rows) == result["ok_trials"]
    assert result["best"]["trial_id"] == rows[0]["id"]
    assert history[0]["allow_network"] is True


def test_sweep_role_mismatch_is_refused_before_loading_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], history: list[dict[str, object]]
) -> None:
    argv = ["--data-root", str(tmp_path / "data"), "backtest", "sweep"]
    assert main([*argv, "--track", "uptrend", "--strategy", "test_sma_cross_short"]) == 2
    assert "expected 'uptrend'" in json.loads(capsys.readouterr().err)["error"]
    assert history == []


def test_sweep_with_every_trial_failing_is_a_technical_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    history: list[dict[str, object]],
) -> None:
    from hypervector.sweep.search import TrialResult

    monkeypatch.setattr(
        "hypervector.sweep.search.run_grid_search",
        lambda *_a, **_k: [
            TrialResult("test_sma_cross_long", "uptrend", {}, status="error", error="boom")
        ],
    )
    argv = ["--data-root", str(tmp_path / "data"), "backtest", "sweep"]
    assert main([*argv, "--track", "uptrend", "--strategy", "test_sma_cross_long"]) == 1
    # stderr carries the settings and board first; the error document is last.
    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "every sweep trial failed" in error["error"]


def test_run_sweep_honours_no_network_for_pipeline_callers(
    tmp_path: Path, history: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.commands.registry import build_parser
    from hypervector.commands.sweep import run_sweep

    args = build_parser().parse_args(
        [
            "--data-root",
            str(tmp_path / "data"),
            "backtest",
            "sweep",
            "--track",
            "downtrend",
            "--strategy",
            "test_sma_cross_short",
            "--no-export",
        ]
    )
    args.no_network = True
    result = run_sweep(args, "downtrend")
    assert result["export_dir"] is None and result["artifacts"]["export"] is None
    assert history[0]["allow_network"] is False


# --- backtest report --------------------------------------------------------------


def _board_fixture(data: Path) -> None:
    database = RunsDB(data / "runs" / "hypervector.db")
    try:
        database.insert_trials(
            [
                _trial(
                    50.0,
                    run_id="sweep-a",
                    strategy="test_sma_cross_long",
                    research_meta={"symbol": "BTC", "timeframe": "1m"},
                ),
                _trial(
                    -20.0,
                    run_id="sweep-b",
                    strategy="test_sma_cross_long",
                    research_meta={"symbol": "ETH", "timeframe": "5m"},
                ),
            ]
        )
    finally:
        database.close()
    logs = data / "logs" / "research"
    logs.mkdir(parents=True)
    board = {
        "strategy": "test_sma_cross_short",
        "symbol": "BTC",
        "timeframe": "5m",
        "lookback_days": 90,
        "sampler_used": "karpathy_random_adaptive",
        "fee_model": "hl_base_taker",
        "all_trials": [
            {"params": {"a": 1}, "metrics": {"net_pnl": 75.0}, "status": "ok"},
            {"params": {"a": 2}, "metrics": {}, "status": "error"},
        ],
    }
    (logs / "autotune_test_sma_cross_short_5m_x.json").write_text(json.dumps(board))
    (logs / "autotune_broken.json").write_text("{")


def test_report_merges_sources_with_filters_and_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _board_fixture(data)
    base = ["--data-root", str(data), "backtest", "report"]

    assert main(base) == 0
    report = json.loads(capsys.readouterr().out)
    assert [(r["source"], r["net_pnl"]) for r in report["rows"]] == [
        ("tune", 75.0),
        ("sweep", 50.0),
        ("sweep", -20.0),
        ("tune", None),
    ]
    assert report["rows"][0]["track"] == "downtrend"
    assert [s["path"].endswith("autotune_broken.json") for s in report["skipped"]] == [
        True
    ]

    assert main([*base, "--source", "sweep", "--symbol", "ETH"]) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]
    assert [(r["run_id"], r["timeframe"]) for r in rows] == [("sweep-b", "5m")]

    assert main([*base, "--track", "downtrend", "--timeframe", "5m"]) == 0
    assert {r["source"] for r in json.loads(capsys.readouterr().out)["rows"]} == {
        "tune"
    }

    assert main([*base, "--limit", "1"]) == 0
    limited = json.loads(capsys.readouterr().out)
    assert (limited["count"], limited["total"]) == (1, 4)

    assert main([*base, "--run-id", "sweep-a", "--format", "table"]) == 0
    table = capsys.readouterr().out
    assert table.splitlines()[0].startswith("source")
    assert "sweep-a" in table and "sweep-b" not in table

    assert main([*base, "--limit", "0"]) == 2


def test_report_is_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "backtest", "report"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert not data.exists()


# --- nautilus ---------------------------------------------------------------------


@pytest.fixture
def phase2_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        report = tmp_path / "summary.json"
        report.write_text(json.dumps({"run_id": "n1", "bars": 10}))
        return SimpleNamespace(
            export_dir=Path(str(kwargs["export_dir"])),
            orders_count=0,
            pnl=-1.5,
            report_path=report,
            loadout_summary={},
        )

    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", fake_run)
    return calls


def test_nautilus_run_defaults_to_the_bundle_lookback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    phase2_calls: list[dict[str, object]],
) -> None:
    data = tmp_path / "data"
    bundle = _strict_export(data, "naut", lookback_days=180)
    base = ["--data-root", str(data), "nautilus", "run", "--export", "naut"]
    assert main([*base, "--no-network"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert phase2_calls[0]["lookback_days"] == 180
    assert phase2_calls[0]["allow_network"] is False
    assert Path(str(phase2_calls[0]["export_dir"])) == bundle.resolve()
    assert (out["lookback_days"], out["lookback_source"]) == (180, "export")
    validation = out["artifacts"]["validation"]
    assert validation["report_path"] == str(tmp_path / "summary.json")
    assert validation["valid"] is True
    assert main([*base, "--lookback-days", "60"]) == 0
    assert phase2_calls[1]["lookback_days"] == 60


def test_nautilus_run_technical_errors_are_json_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class EngineError(Exception):
        pass

    def broken(**_kwargs: object) -> None:
        raise EngineError("offline history cache missing")

    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", broken)
    data = tmp_path / "data"
    _strict_export(data, "btc_err")
    assert (
        main(["--data-root", str(data), "nautilus", "run", "--export", "btc_err"]) == 1
    )
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["error_type"] == "EngineError"
    assert error["command"] == "nautilus run"


def test_nautilus_run_refuses_symbols_without_venue_geometry_before_the_engine(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    phase2_calls: list[dict[str, object]],
) -> None:
    data = tmp_path / "data"
    _strict_export(data, "doge", symbol="DOGE")
    assert main(["--data-root", str(data), "nautilus", "run", "--export", "doge"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["command"] == "nautilus run"
    assert "does not support symbol 'DOGE'" in error["error"]
    assert phase2_calls == []


def test_nautilus_run_routes_built_in_non_btc_symbols_to_the_engine(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    phase2_calls: list[dict[str, object]],
) -> None:
    data = tmp_path / "data"
    _strict_export(data, "eth", symbol="ETH")
    assert main(["--data-root", str(data), "nautilus", "run", "--export", "eth"]) == 0
    assert len(phase2_calls) == 1
    assert phase2_calls[0]["conviction"] is None
    assert phase2_calls[0]["signal_mode"] == "auto"
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_nautilus_check_never_creates_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    argv = ["--data-root", str(data), "nautilus", "check", "--export", "missing"]
    assert main(argv) == 2
    assert not data.exists()
    bundle = _strict_export(tmp_path / "elsewhere", "chk")
    argv = ["--data-root", str(data), "nautilus", "check", "--export", str(bundle)]
    assert main([*argv, "--no-nautilus-probe"]) == 0
    assert json.loads(capsys.readouterr().out)["export_dir"] == str(bundle.resolve())
    assert not data.exists()


def test_nautilus_catalog_writes_recorded_events(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_write(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            book_delta_count=4,
            quote_count=2,
            trade_count=1,
            gap_count=0,
            gap_provenance_path=Path(str(kwargs["catalog_path"])) / "gaps.json",
        )

    monkeypatch.setattr(
        "hypervector.nautilus.hl_catalog.write_hyperliquid_catalog", fake_write
    )
    data = tmp_path / "data"
    base = ["--data-root", str(data), "nautilus", "catalog", "--symbol", "BTC"]
    precision = ["--price-precision", "1", "--size-precision", "5"]
    assert main([*base, *precision]) == 1
    assert "no recorded public events" in json.loads(capsys.readouterr().err)["error"]

    (data / "cache" / "events" / "hyperliquid" / "BTC").mkdir(parents=True)
    assert main([*base, *precision]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["instrument_id"] == "BTC-PERP.HYPERLIQUID"
    assert out["catalog_path"] == str((data / "nautilus" / "catalog" / "BTC").resolve())
    assert captured["price_precision"] == 1 and captured["size_precision"] == 5
    assert main([*base, "--price-precision", "-1", "--size-precision", "5"]) == 2


# --- paper run --------------------------------------------------------------------


@pytest.fixture
def daemon_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[dict[str, object]]:
    from hypervector.paper.runner import PaperDaemonResult

    calls: list[dict[str, object]] = []

    def fake_daemon(**kwargs: object) -> PaperDaemonResult:
        calls.append(
            {
                **kwargs,
                "metalabel_root": os.environ.get("HYPERVECTOR_METALABEL_ROOT"),
            }
        )
        return PaperDaemonResult(
            run_id="p1",
            export_dir=Path(str(kwargs["export_dir"])),
            decisions_path=tmp_path / "decisions.jsonl",
            warm_bars=0,
            live_bars=0,
            bars_processed=0,
            fills_count=0,
            stop_reason="bounded",
            execution_mode=str(kwargs["execution_mode"]),
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)
    monkeypatch.delenv("HYPERVECTOR_METALABEL_ROOT", raising=False)
    return calls


def test_paper_run_resolves_candidate_ids_and_metalabel_bundles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    daemon_calls: list[dict[str, object]],
) -> None:
    data = tmp_path / "data"
    bundle = _strict_export(data, "paper_cand")
    model = data / "models" / "metalabel" / "wf_x"
    model.mkdir(parents=True)
    (model / "metalabel_lgbm.txt").write_text("tree\n")
    (model / "metalabel_metadata.json").write_text("{}")
    argv = ["--data-root", str(data), "paper", "run", "--export", "paper_cand"]
    assert main([*argv, "--metalabel-bundle", "latest"]) == 0
    out = json.loads(capsys.readouterr().out)
    [call] = daemon_calls
    assert Path(str(call["export_dir"])) == bundle.resolve()
    assert call["metalabel_root"] == str(model.resolve())
    assert out["metalabel_bundle"] == str(model.resolve())
    assert out["artifacts"] == {
        "export": str(bundle.resolve()),
        "model": str(model.resolve()),
        "paper": str(tmp_path / "decisions.jsonl"),
    }
    # The model override lasts for the session only.
    assert "HYPERVECTOR_METALABEL_ROOT" not in os.environ
    assert main([*argv, "--metalabel-bundle", "nope"]) == 2
    assert main(["--data-root", str(data), "paper", "run", "--export", "gone"]) == 2


# --- model train ------------------------------------------------------------------


def test_model_train_factors_training_and_keeps_the_json_error_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.commands.model import train_metalabel_bundle

    data = tmp_path / "data"
    bundle = _strict_export(data, "ml")
    calls: list[dict[str, object]] = []

    def fake_train(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            bundle_dir=tmp_path / "model", report={"ok": True, "n": 3}
        )

    monkeypatch.setattr(
        "hypervector.ml.walk_forward.run_walk_forward_metalabel", fake_train
    )
    report = train_metalabel_bundle(export_dir=bundle, data_root=data, train_days=30)
    assert report == {
        "ok": True,
        "n": 3,
        "bundle_dir": str((tmp_path / "model").resolve()),
    }
    assert calls[0]["train_days"] == 30 and calls[0]["lookback_days"] is None

    assert main(["--data-root", str(data), "model", "train", "--export", "latest"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["artifacts"]["model"] == str((tmp_path / "model").resolve())
    assert out["export_dir"] == str(bundle.resolve())
    assert f"hypervector --data-root {data} paper run --export ml " in out["paper_hint"]

    outside = _strict_export(tmp_path / "elsewhere", "ml_out")
    argv = ["--data-root", str(data), "model", "train", "--export", str(outside)]
    assert main(argv) == 0
    hint = json.loads(capsys.readouterr().out)["paper_hint"]
    assert f"--export {outside.resolve()} " in hint

    class LightGBMError(Exception):
        pass

    def broken(**_kwargs: object) -> None:
        raise LightGBMError("training data is degenerate")

    monkeypatch.setattr(
        "hypervector.ml.walk_forward.run_walk_forward_metalabel", broken
    )
    assert main(["--data-root", str(data), "model", "train", "--export", "ml"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["error_type"] == "LightGBMError"


# --- regime -----------------------------------------------------------------------


def test_regime_classify_uses_the_canonical_engine_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import hypervector.regime.ultimate as ultimate

    frame = fixture_ohlcv(n_bars=300, drift=5.0)
    seen: list[object] = []
    real = ultimate.detect_ultimate_regime

    def spy(df, *args, **kwargs):
        seen.append(type(df.index).__name__)
        return real(df, *args, **kwargs)

    monkeypatch.setattr(ultimate, "detect_ultimate_regime", spy)
    monkeypatch.setattr(
        "hypervector.commands.regime._load_bars",
        lambda _args: (frame, {"fixture": True}),
    )
    assert main(["--data-root", str(tmp_path), "regime", "classify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["detector"] == "canonical" and seen == ["DatetimeIndex"]
    assert sum(out["metrics"]["pct_by_state"].values()) == pytest.approx(1.0)
    assert out["metrics"]["n_bars"] == 300


@pytest.mark.parametrize(
    "extra",
    [
        ["--fast", "5"],
        ["--timeframe", "5m"],
        ["--detector", "ema", "--fast", "48", "--slow", "12"],
    ],
)
def test_regime_classify_refuses_bad_detector_options_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: list[str]
) -> None:
    def fail(_args: argparse.Namespace) -> None:
        raise AssertionError("data loaded before validation")

    monkeypatch.setattr("hypervector.commands.regime._load_bars", fail)
    assert main(["--data-root", str(tmp_path), "regime", "classify", *extra]) == 2


# --- live check -------------------------------------------------------------------


@pytest.fixture
def dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point credential presence at a scratch .env; clear process credentials."""
    import hypervector.runtime_env as runtime_env

    path = tmp_path / ".env"
    real = runtime_env.dotenv_key_presence
    monkeypatch.setattr(
        runtime_env,
        "dotenv_key_presence",
        lambda keys, **kwargs: real(keys, candidates=[path], **kwargs),
    )
    monkeypatch.delenv(WALLET, raising=False)
    monkeypatch.delenv(SIGNING_KEY, raising=False)
    return path


def test_live_check_without_a_profile_is_not_ready(
    dotenv: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["live", "check"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False and report["profile"] is None
    assert report["credentials"]["wallet_configured"] is False
    assert any("--config" in blocker for blocker in report["blockers"])
    assert report["authority"] == {
        "enabled": False,
        "i_accept_live_risk": False,
        "would_arm": False,
    }


def test_live_check_reports_credential_presence_as_booleans_only(
    dotenv: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "0xsecret-signing-key-value"
    dotenv.write_text(f"{SIGNING_KEY}={secret}\n")
    monkeypatch.setenv(WALLET, "0xpublicwallet")
    assert main(["live", "check", "--armed", "--enabled"]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    keys = report["credentials"]["keys"]
    assert keys[WALLET] == {"configured": True, "source": "process_env"}
    assert keys[SIGNING_KEY] == {"configured": True, "source": "dotenv"}
    assert report["authority"]["would_arm"] is True
    assert secret not in output and "0xpublicwallet" not in output
    assert SIGNING_KEY not in os.environ


def _fake_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    ledger = tmp_path / "live" / "bidirectional_cohort" / "cohort.jsonl"
    ledger.parent.mkdir(parents=True)
    config = SimpleNamespace(
        profile_id="profile-x",
        profile_fingerprint="f" * 64,
        stop_file=ledger.parent / "STOP",
        cohort_ledger=ledger,
    )
    modes: list[str] = []

    def load(path: Path, *, mode: str) -> SimpleNamespace:
        modes.append(mode)
        return config

    monkeypatch.setattr(
        "hypervector.live.multi_asset_live_config.load_multi_asset_live_config", load
    )
    return config, modes


def test_live_check_with_a_ready_profile_exits_zero(
    dotenv: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config, modes = _fake_profile(monkeypatch, tmp_path)
    dotenv.write_text(f"{WALLET}=0xw\n{SIGNING_KEY}=0xk\n")
    argv = ["live", "check", "--config", "p.toml", "--enabled", "--i-accept-live-risk"]
    assert main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is True and report["blockers"] == []
    assert modes == ["observe"]
    profile = report["profile"]
    assert profile["profile_fingerprint"] == "f" * 64
    assert "provider_dependencies_ok" not in profile
    assert profile["stop_file"]["present"] is False

    config.stop_file.write_text("stop\n")
    (config.cohort_ledger.parent / "transition_drain.json").write_text("{}")
    assert main(argv) == 1
    blockers = json.loads(capsys.readouterr().out)["blockers"]
    assert any("STOP file present" in b for b in blockers)
    assert any("transition drain evidence remains" in b for b in blockers)


def test_live_check_reports_a_profile_that_does_not_load(
    dotenv: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _fake_profile(monkeypatch, tmp_path)

    def broken(path: Path, *, mode: str) -> None:
        raise ValueError("unknown key in [runtime]")

    monkeypatch.setattr(
        "hypervector.live.multi_asset_live_config.load_multi_asset_live_config", broken
    )
    assert main(["live", "check", "--config", "p.toml"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["profile"]["loaded"] is False
    assert any("does not load in observe mode" in b for b in report["blockers"])


def test_live_check_without_a_profile_imports_no_engine(tmp_path: Path) -> None:
    heavy = ("pandas", "numpy", "vectorbt", "nautilus_trader", "duckdb", "hyperliquid")
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        "main(['live', 'check'])\n"
        f"loaded = sorted(set({heavy!r}) & set(sys.modules))\n"
        "assert not loaded, loaded\n"
    )
    source_root = Path(hypervector.__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=60,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(source_root)},
        stdout=subprocess.DEVNULL,
    )


# --- tune strategy ----------------------------------------------------------------


def test_tune_strategy_refuses_an_unavailable_optuna_before_loading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_kwargs: object) -> None:
        raise AssertionError("search ran")

    monkeypatch.setattr("hypervector.sweep.autotune.run_optuna_autotune", fail)
    monkeypatch.setattr("hypervector.commands.autotune.find_spec", lambda _name: None)
    base = ["--data-root", str(tmp_path / "data"), "tune", "strategy"]
    assert main([*base, "--sampler", "optuna"]) == 2
    assert "optuna" in json.loads(capsys.readouterr().err)["error"]
    assert main([*base, "--strategy", "no_such_strategy"]) == 2
    assert not (tmp_path / "data").exists()


def test_tune_strategy_reports_board_and_export_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = SimpleNamespace(
        strategy_name="test_sma_cross_long",
        symbol="BTC",
        timeframe="1m",
        lookback_days=90,
        n_trials=2,
        sampler_used="karpathy_random_adaptive",
        best_params={},
        best_exit_cfg={},
        best_metrics={"net_pnl": -3.0},
        export_dir=tmp_path / "exports" / "auto_1",
        board_path=tmp_path / "board.json",
    )
    monkeypatch.setattr(
        "hypervector.sweep.autotune.run_optuna_autotune", lambda **_kwargs: result
    )
    argv = ["--data-root", str(tmp_path), "tune", "strategy", "--n-trials", "2"]
    assert main([*argv, "--strategy", "test_sma_cross_long"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["artifacts"] == {
        "board": str(tmp_path / "board.json"),
        "export": str(tmp_path / "exports" / "auto_1"),
    }
    assert out["candidate_id"] == "auto_1"


# --- data history -------------------------------------------------------------------


def test_data_history_reports_the_dataset_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], history: list[dict[str, object]]
) -> None:
    data = tmp_path / "data"
    assert (
        main(["--data-root", str(data), "data", "history", "--lookback-days", "30"])
        == 0
    )
    dataset = json.loads(capsys.readouterr().out)["artifacts"]["dataset"]
    assert dataset["rows"] == 400 and dataset["symbol"] == "BTC"
    assert dataset["start"] < dataset["end"]
    assert dataset["cache_path"] == str(
        (data / "cache" / "BTC_1m_30d.parquet").resolve()
    )


def test_trial_rows_with_failed_queries_still_close_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The board's database handle is released even when a query fails.

    The failure itself is a technical failure: error JSON and exit 1.
    """
    database = RunsDB(tmp_path / "runs" / "hypervector.db")
    monkeypatch.setattr("hypervector.commands.sweep.RunsDB", lambda _path: database)

    def refuse(**_kwargs: object) -> list[dict[str, object]]:
        raise sqlite3.OperationalError("injected")

    monkeypatch.setattr(database, "list_trials", refuse)
    argv = ["--data-root", str(tmp_path), "backtest", "report", "--source", "sweep"]
    assert main(argv) == 1
    error = json.loads(capsys.readouterr().err)
    assert (error["error_type"], error["error"]) == ("OperationalError", "injected")
    with pytest.raises(sqlite3.ProgrammingError):
        database.init_schema()
