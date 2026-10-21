"""Engine fixes wired into the unified CLI: specs, handlers and output contracts.

Every test is offline: loaders, engines and vendor calls are replaced, and all
writes land under ``tmp_path``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from hypervector.cli import main
from hypervector.commands.registry import build_parser, spec_for
from hypervector.data.provenance import summarize_provenance
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate

WINDOW = ["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-01T03:00:00Z"]


class Boundary(Exception):
    """Raised by a fake engine once the arguments it received are recorded."""


def _default(command: str, flag: str) -> object:
    [argument] = [a for a in spec_for(command)["arguments"] if a["flags"][0] == flag]
    return argument["options"].get("default")


def _default_help(command: str, flag: str) -> object:
    [argument] = [a for a in spec_for(command)["arguments"] if a["flags"][0] == flag]
    return argument["options"].get("help")


def _bars(n_bars: int = 300):
    return fixture_ohlcv(n_bars=n_bars, drift=20.0, wave_period=30, source="hl")


@pytest.fixture
def history(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Offline research history for every loader path; records each request."""
    calls: list[dict[str, object]] = []
    frame = _bars()

    def fake_load(data_root: object, **kwargs: object):
        calls.append({"data_root": data_root, **kwargs})
        return frame, summarize_provenance(frame)

    monkeypatch.setattr("hypervector.data.pipeline.load_research_history", fake_load)
    return calls


def _strict_export(
    data: Path, name: str, *, symbol: str = "BTC", apply_costs: bool | None = None
) -> Path:
    meta: dict[str, object] = {
        "symbol": symbol,
        "timeframe": "1m",
        "track": "downtrend",
        "lookback_days": 45,
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
        "costs": {"taker_fee": 0.00045, "slippage_bps": 2.0},
        "risk": {"risk_pct_min": 0.01, "risk_pct_max": 0.05},
    }
    if apply_costs is not None:
        meta["apply_costs"] = apply_costs
    return export_candidate(
        data / "exports",
        run_id=f"run-{name}",
        meta=meta,
        params={"strategy": "test_sma_cross_short", "role": "downtrend"},
        metrics={"net_pnl": -5.0, "trade_count": 2},
        candidate_id=name,
        strict=True,
    )


# --- parse-time converters ---------------------------------------------------------


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0", "-5", "fifty"])
def test_live_run_max_notional_must_be_finite_and_positive_at_parse(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["live", "run", "--export", "x", "--max-notional-usd", value]
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(argv)
    assert exc.value.code == 2
    assert "--max-notional-usd" in capsys.readouterr().err


def test_live_run_max_notional_accepts_a_finite_cap() -> None:
    args = build_parser().parse_args(
        ["live", "run", "--export", "x", "--max-notional-usd", "25"]
    )
    assert args.max_notional_usd == 25.0


# --- archive fetch defaults ----------------------------------------------------------


def test_archive_fetch_page_defaults_complete_a_normal_window() -> None:
    from hypervector.data.oxa_history import DEFAULT_BOOK_MAX_PAGES
    from hypervector.data.oxa_prices import OxaPriceRequest
    from hypervector.data.oxa_trades import DEFAULT_TRADE_MAX_PAGES

    assert _default("archive book-fetch", "--max-pages") == DEFAULT_BOOK_MAX_PAGES
    assert _default("archive trade-fetch", "--max-pages") == DEFAULT_TRADE_MAX_PAGES
    price_default = OxaPriceRequest.__dataclass_fields__["max_pages"].default
    assert _default("archive price-fetch", "--max-pages") == price_default
    assert _default("archive liquidation-fetch", "--max-pages") == 250
    assert _default("archive candle-fetch", "--max-pages") is None


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("book-fetch", "hypervector.data.oxa_history.acquire_and_store_orderbooks"),
        ("trade-fetch", "hypervector.data.oxa_trades.acquire_and_store_trades"),
        (
            "liquidation-fetch",
            "hypervector.data.oxa_liquidations.acquire_and_store_liquidations",
        ),
    ],
)
@pytest.mark.parametrize("partial", [False, True])
def test_allow_partial_reaches_the_acquisition_only_when_requested(
    command: str,
    target: str,
    partial: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(target, fake)
    argv = ["--data-root", str(tmp_path), "archive", command, *WINDOW]
    assert main([*argv, "--allow-partial"] if partial else argv) == 0
    assert seen.get("allow_partial", False) is partial
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_price_fetch_has_no_partial_mode() -> None:
    flags = {a["flags"][0] for a in spec_for("archive price-fetch")["arguments"]}
    assert "--allow-partial" not in flags


def test_candle_fetch_derives_its_page_budget_from_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.data.oxa_candles import estimated_candle_pages

    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("hypervector.data.oxa_candles.acquire_and_store_candles", fake)
    assert main(["--data-root", str(tmp_path), "archive", "candle-fetch", *WINDOW]) == 0
    request = seen["request"]
    assert request.max_pages == estimated_candle_pages(request)  # type: ignore[attr-defined]


# --- archive backfill ----------------------------------------------------------------


def test_backfill_invalid_flag_combination_is_refused_with_error_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hypervector.operations.oxa_backfill as backfill

    monkeypatch.setattr(
        backfill, "run_oxa_backfill", lambda *_a, **_k: pytest.fail("job started")
    )
    argv = ["--data-root", str(tmp_path), "archive", "backfill", *WINDOW]
    assert main([*argv, "--books-only", "--include-prices"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["command"] == "archive backfill"
    assert "book_only" in error["error"]
    assert main([*argv, "--workers", "11"]) == 2
    assert not tmp_path.joinpath("cache").exists()


def test_backfill_page_bounds_reach_the_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hypervector.operations.oxa_backfill as backfill

    seen: dict[str, object] = {}

    def fake(config: object, **_kwargs: object) -> tuple[object, ...]:
        seen["config"] = config
        return ()

    monkeypatch.setattr(backfill, "run_oxa_backfill", fake)
    argv = ["--data-root", str(tmp_path), "archive", "backfill", *WINDOW]
    assert main([*argv, "--book-max-pages", "7", "--trade-max-pages", "9"]) == 0
    config = seen["config"]
    assert (config.book_max_pages, config.trade_max_pages) == (7, 9)  # type: ignore[attr-defined]
    assert config.price_max_pages == 20  # type: ignore[attr-defined]
    capsys.readouterr()


# --- archive repair-trades -------------------------------------------------------------


def _trade_bundle(tmp_path: Path, version: str = "legacy_v1") -> Path:
    bundle = tmp_path / "BTC_20260101T0000_trades"
    bundle.mkdir()
    (bundle / "manifest.json").write_text(
        json.dumps({"normalization_version": version}), encoding="utf-8"
    )
    return bundle


@pytest.mark.parametrize("apply", [False, True])
def test_repair_trades_previews_then_applies(
    apply: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hypervector.data.oxa_trade_repair import TradeBundleRepair

    bundle = _trade_bundle(tmp_path)
    seen: list[bool] = []

    def fake(directory: Path, *, apply: bool = False) -> TradeBundleRepair:
        seen.append(apply)
        backup = directory.with_name(directory.name + ".pre_taker_only_v2")
        return TradeBundleRepair(directory, backup, 10, 7, 12, apply)

    monkeypatch.setattr("hypervector.data.oxa_trade_repair.repair_trade_bundle", fake)
    argv = ["--data-root", str(tmp_path), "archive", "repair-trades"]
    argv += ["--bundle", str(bundle), *(["--apply"] if apply else [])]
    assert main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert seen == [apply]
    assert report["mode"] == ("apply" if apply else "preview")
    assert (report["previous_trade_count"], report["repaired_trade_count"]) == (10, 7)
    assert report["applied"] is apply
    assert report["already_current"] is False
    assert ("--replace-changed" in report["next_step"]) is apply
    assert ("--apply" in report["next_step"]) is not apply


def test_repair_trades_refuses_a_directory_that_is_not_a_trade_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hypervector.data.oxa_trade_repair.repair_trade_bundle",
        lambda *_a, **_k: pytest.fail("repair ran"),
    )
    other = tmp_path / "BTC_books"
    other.mkdir()
    argv = ["--data-root", str(tmp_path), "archive", "repair-trades", "--bundle"]
    assert main([*argv, str(other)]) == 2
    assert "not a stored trade bundle" in json.loads(capsys.readouterr().err)["error"]


# --- db build ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flags", "mode", "verify_all"),
    [
        ([], "incremental", False),
        (["--replace-changed"], "replace_changed", False),
        (["--replace-changed", "--verify-all"], "replace_changed", True),
    ],
)
def test_db_build_exposes_replace_changed_and_verify_all(
    flags: list[str],
    mode: str,
    verify_all: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, bool]] = []
    ingest = SimpleNamespace(to_dict=lambda: {"bundles": 0})

    class FakeDatabase:
        def __init__(self, _path: Path) -> None:
            pass

        def ingest_archive(self, _config: object, *, verify_all: bool) -> object:
            calls.append(("incremental", verify_all))
            return ingest

        def replace_changed_archive(self, _config: object, *, verify_all: bool) -> object:
            calls.append(("replace_changed", verify_all))
            return ingest

        def summary(self) -> dict[str, object]:
            return {}

    monkeypatch.setattr(
        "hypervector.data.research_database.ResearchDatabase", FakeDatabase
    )
    argv = ["--data-root", str(tmp_path), "db", "build", *WINDOW, *flags]
    argv += ["--database", str(tmp_path / "market.duckdb")]
    assert main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert calls == [(mode, verify_all)]
    assert (report["mode"], report["verify_all"]) == (mode, verify_all)


# --- tune strategy -------------------------------------------------------------------------


def test_tune_strategy_passes_objective_and_train_fraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake(**kwargs: object) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(
            strategy_name="test_sma_cross_long",
            symbol="BTC",
            timeframe="1m",
            lookback_days=90,
            n_trials=3,
            n_trials_requested=5,
            space_exhausted=True,
            sampler_used="karpathy_random_adaptive",
            objective="sharpe",
            selection_basis="full_window_in_sample",
            best_trial_number=2,
            best_trade_count=4,
            best_params={},
            best_exit_cfg={},
            best_metrics={"sharpe": 1.0},
            train_metrics={"sharpe": 1.0},
            holdout_metrics=None,
            warnings=["search space exhausted after 3 trials"],
            export_dir=None,
            board_path=tmp_path / "board.json",
        )

    monkeypatch.setattr("hypervector.sweep.autotune.run_optuna_autotune", fake)
    argv = ["--data-root", str(tmp_path), "tune", "strategy", "--n-trials", "5"]
    argv += ["--strategy", "test_sma_cross_long"]
    assert main([*argv, "--objective", "sharpe", "--train-fraction", "1.0"]) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert (seen["objective"], seen["train_fraction"]) == ("sharpe", 1.0)
    for key in (
        "objective",
        "selection_basis",
        "train_metrics",
        "holdout_metrics",
        "best_trial_number",
        "best_trade_count",
        "n_trials_requested",
        "space_exhausted",
        "warnings",
    ):
        assert key in out, key
    assert out["objective"] == "sharpe" and out["n_trials_requested"] == 5
    assert "warning: search space exhausted" in captured.err


def test_tune_strategy_defaults_to_net_pnl_with_a_holdout() -> None:
    args = build_parser().parse_args(["tune", "strategy"])
    assert (args.objective, args.train_fraction) == ("net_pnl", 0.7)


@pytest.mark.parametrize("value", ["0", "1.5", "nan"])
def test_tune_strategy_refuses_a_train_fraction_outside_the_unit_interval(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hypervector.sweep.autotune.run_optuna_autotune",
        lambda **_k: pytest.fail("search ran"),
    )
    argv = ["--data-root", str(tmp_path), "tune", "strategy", "--train-fraction", value]
    assert main(argv) == 2


def test_sampler_help_lists_only_the_two_samplers() -> None:
    [sampler] = [
        a for a in spec_for("tune strategy")["arguments"] if a["flags"] == ["--sampler"]
    ]
    assert sampler["options"]["choices"] == ["karpathy", "optuna"]
    assert "hybrid" not in sampler["options"]["help"]


# --- backtest run / sweep -------------------------------------------------------------------


def test_backtest_leverage_above_the_venue_cap_is_refused_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hypervector.commands.backtest._load_bars",
        lambda _args: pytest.fail("data loaded before the leverage check"),
    )
    argv = ["--data-root", str(tmp_path), "backtest", "run", "--symbol", "ETH"]
    argv += ["--strategy", "test_sma_cross_long"]
    assert main([*argv, "--leverage", "30"]) == 2
    assert "venue cap of 25x" in json.loads(capsys.readouterr().err)["error"]
    assert main([*argv, "--leverage", "nan"]) == 2


def test_backtest_passes_symbol_and_normalized_direction_and_reports_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import pandas as pd

    from hypervector.strategies.registry import StrategySpec, register

    bars = _bars(120)
    provenance = summarize_provenance(bars)
    monkeypatch.setattr(
        "hypervector.commands.backtest._load_bars", lambda _args: (bars, provenance)
    )

    def build(df: pd.DataFrame, **_kwargs: object):
        flags = pd.Series(False, index=df.index)
        return flags, flags, "breakout_short"

    register(StrategySpec("tagged_fake", "downtrend", {}, build))
    seen: dict[str, object] = {}

    def fake_metrics(*_args: object, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {
            "net_pnl": 0.0,
            "total_return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_pct": 0.0,
            "liquidations": 0,
            "min_equity": 10_000.0,
            "equity_depleted": False,
            "effective_risk_pct": 0.0,
            "bar_freq": "1min",
            "stop_fill_model": "intrabar_ohlc_stopmarket",
        }

    monkeypatch.setattr("hypervector.sweep.metrics.compute_trial_metrics", fake_metrics)
    argv = ["--data-root", str(tmp_path), "backtest", "run", "--symbol", "SOL"]
    assert main([*argv, "--strategy", "tagged_fake", "--leverage", "20"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (seen["symbol"], seen["direction"]) == ("SOL", "short")
    assert seen["risk_cfg"].max_size_frac == 20.0  # type: ignore[attr-defined]
    assert out["data_provenance"] == json.loads(json.dumps(provenance, default=str))
    assert out["data_window"]["bar_count"] == 120
    metrics = out["metrics"]
    assert (metrics["liquidations"], metrics["equity_depleted"]) == (0, False)
    assert out["model"]["stop_fill_model"] == "intrabar_ohlc_stopmarket"


def test_backtest_leverage_help_names_the_venue_caps() -> None:
    text = str(_default_help("backtest run", "--leverage"))
    assert "1.0..10.0" not in text
    assert "BTC 40" in text and "ETH 25" in text and "SOL 20" in text


def test_sweep_refuses_leverage_above_the_cap_and_passes_the_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}

    def fake_search(*_args: object, **kwargs: object) -> list[object]:
        seen.update(kwargs)
        raise Boundary

    monkeypatch.setattr("hypervector.sweep.search.run_grid_search", fake_search)
    base = ["--data-root", str(tmp_path), "backtest", "sweep", "--track", "uptrend"]
    base += ["--strategy", "test_sma_cross_long"]
    assert main([*base, "--symbol", "SOL", "--leverage", "25"]) == 2
    assert "venue cap of 20x" in json.loads(capsys.readouterr().err)["error"]
    assert history == []
    with pytest.raises(Boundary):
        main([*base, "--symbol", "SOL", "--leverage", "5", "--no-export"])
    assert seen["symbol"] == "SOL"
    assert seen["risk_cfg"].max_size_frac == 5.0  # type: ignore[attr-defined]


# --- cache pinning -----------------------------------------------------------------------------


def test_cache_flags_reach_the_history_loader(
    tmp_path: Path,
    history: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    import pandas as pd

    base = ["--data-root", str(tmp_path), "data", "history", "--lookback-days", "30"]
    assert main(base) == 0
    assert "max_cache_age" not in history[-1]
    assert main([*base, "--pin-cache"]) == 0
    assert history[-1]["max_cache_age"] is None
    assert main([*base, "--max-cache-age-hours", "6"]) == 0
    assert history[-1]["max_cache_age"] == pd.Timedelta(hours=6)
    capsys.readouterr()
    calls = len(history)
    assert main([*base, "--pin-cache", "--max-cache-age-hours", "6"]) == 2
    assert main([*base, "--pin-cache", "--refresh"]) == 2
    assert len(history) == calls


# --- data history / book-align ---------------------------------------------------------------


def test_data_history_reports_provenance_and_window(
    tmp_path: Path, history: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--data-root", str(tmp_path), "data", "history", "--lookback-days", "30"]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["provenance"]
    assert out["data_window"]["bar_count"] == 300
    assert out["data_window"]["first_bar_utc"].startswith("2024-01-01")


def test_data_history_failure_is_error_json_with_the_loader_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_root: object, **_kwargs: object) -> None:
        exc = RuntimeError("binance backfill failed")
        exc.add_note(
            "1440 fetched HL bars were kept in cache key BTC_1m_30d_hlonly; "
            "retry later, or pass --strict-hl-only to use HL-only history"
        )
        raise exc

    monkeypatch.setattr("hypervector.data.pipeline.load_research_history", broken)
    argv = ["--data-root", str(tmp_path), "data", "history", "--lookback-days", "30"]
    assert main(argv) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["command"] == "data history"
    assert "BTC_1m_30d_hlonly" in error["notes"][0]
    assert "--strict-hl-only" in error["hint"]


def _far_book(tmp_path: Path) -> Path:
    book = tmp_path / "book.jsonl"
    row = {
        "ts_exchange_ms": 1_000,
        "best_bid": 99.0,
        "best_ask": 101.0,
        "bids": [{"px": 99.0, "sz": 1.0}],
        "asks": [{"px": 101.0, "sz": 1.0}],
    }
    book.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return book


def test_book_align_reports_coverage_and_prints_null_not_nan(
    tmp_path: Path, history: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--data-root", str(tmp_path), "data", "book-align"]
    argv += ["--book-path", str(_far_book(tmp_path)), "--lookback-days", "30"]
    assert main(argv) == 0
    raw = capsys.readouterr().out
    # Strict JSON: a bare NaN/Infinity token would reach parse_constant.
    out = json.loads(raw, parse_constant=lambda token: pytest.fail(f"bare {token}"))
    assert (out["matched_bars"], out["book_coverage"]) == (0, 0.0)
    assert out["warnings"] and out["data_window"]["bar_count"] == 300
    assert all(row["spread_bps"] is None for row in out["sample"])


def test_book_align_min_coverage_is_an_opt_in_failure(
    tmp_path: Path, history: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--data-root", str(tmp_path), "data", "book-align", "--lookback-days", "30"]
    argv += ["--book-path", str(_far_book(tmp_path)), "--min-coverage", "0.5"]
    assert main(argv) == 1
    report = json.loads(capsys.readouterr().err)
    assert report["ok"] is False and report["min_coverage"] == 0.5


def test_book_align_refuses_a_missing_book_before_loading(
    tmp_path: Path, history: list[dict[str, object]]
) -> None:
    argv = ["--data-root", str(tmp_path), "data", "book-align"]
    assert main([*argv, "--book-path", str(tmp_path / "missing.jsonl")]) == 2
    assert history == []


def test_book_record_forwards_the_error_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake(_root: object, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"ok": True, "errors": 0, "last_error": None}

    monkeypatch.setattr("hypervector.data.book_record.run_book_recorder", fake)
    argv = ["--data-root", str(tmp_path), "data", "book-record", "--max-snapshots", "1"]
    assert main([*argv, "--max-consecutive-errors", "3"]) == 0
    assert seen["max_consecutive_errors"] == 3
    assert json.loads(capsys.readouterr().out)["last_error"] is None


# --- regime book path ----------------------------------------------------------------------


@pytest.mark.parametrize("command", [["regime", "eval"], ["regime", "export"]])
def test_regime_missing_book_path_is_refused_before_loading(
    command: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hypervector.commands.regime._load_bars",
        lambda _args: pytest.fail("data loaded before the book check"),
    )
    argv = ["--data-root", str(tmp_path), *command]
    assert main([*argv, "--book-path", str(tmp_path / "missing.jsonl")]) == 2


# --- nautilus ------------------------------------------------------------------------------


@pytest.fixture
def phase2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    summary = {
        "run_id": "n1",
        "bars": 10,
        "conviction": 0.4,
        "conviction_source": "export_meta",
        "trade_count": 3,
        "pnl_basis": "mark_to_market_net_of_fees_and_funding",
        "pnl_realized": -1.0,
        "pnl_unrealized": 0.5,
        "pnl_before_funding": -0.5,
        "funding_cost": 0.1,
        "commissions_total": 0.2,
        "open_positions_at_end": 1,
        "signal_mode_used": "precomputed",
        "instrument_id": "ETH-PERP.HYPERLIQUID",
    }

    def fake_run(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        report = tmp_path / "summary.json"
        report.write_text(json.dumps(summary), encoding="utf-8")
        return SimpleNamespace(
            export_dir=Path(str(kwargs["export_dir"])),
            orders_count=4,
            pnl=-0.6,
            report_path=report,
            loadout_summary={},
        )

    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", fake_run)
    return calls


def test_nautilus_run_uses_the_bundle_conviction_and_echoes_the_summary(
    tmp_path: Path, phase2: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _strict_export(data, "eth", symbol="ETH")
    base = ["--data-root", str(data), "nautilus", "run", "--export", "eth"]
    assert main(base) == 0
    out = json.loads(capsys.readouterr().out)
    assert phase2[0]["conviction"] is None
    assert (out["conviction"], out["conviction_source"]) == (0.4, "export_meta")
    assert (out["trade_count"], out["pnl_realized"], out["pnl_unrealized"]) == (
        3,
        -1.0,
        0.5,
    )
    assert out["instrument_id"] == "ETH-PERP.HYPERLIQUID"
    assert main([*base, "--conviction", "0.3", "--signal-mode", "windowed"]) == 0
    assert (phase2[1]["conviction"], phase2[1]["signal_mode"]) == (0.3, "windowed")
    capsys.readouterr()
    assert main([*base, "--conviction", "1.5"]) == 2
    assert len(phase2) == 2


def test_nautilus_run_technical_failure_carries_the_first_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.nautilus.errors import Phase2TechnicalFailure

    def broken(**_kwargs: object) -> None:
        raise Phase2TechnicalFailure(
            "strategy raised on bar 7", strategy="test_sma_cross_short", first_error="boom"
        )

    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", broken)
    data = tmp_path / "data"
    _strict_export(data, "btc")
    assert main(["--data-root", str(data), "nautilus", "run", "--export", "btc"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error_type"] == "Phase2TechnicalFailure"
    assert (error["strategy"], error["first_error"]) == ("test_sma_cross_short", "boom")


def test_nautilus_run_engine_unsupported_symbol_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.nautilus.errors import UnsupportedNautilusSymbol

    def unsupported(**_kwargs: object) -> None:
        raise UnsupportedNautilusSymbol("BTC", "metadata changed")

    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", unsupported)
    data = tmp_path / "data"
    _strict_export(data, "btc")
    assert main(["--data-root", str(data), "nautilus", "run", "--export", "btc"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error_type"] == "UnsupportedNautilusSymbol"
    assert error["reason"] == "metadata changed"


def test_nautilus_run_accepts_cached_venue_metadata_for_other_perps(
    tmp_path: Path, phase2: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    bundle = _strict_export(data, "doge", symbol="DOGE")
    meta = json.loads((bundle / "meta.json").read_text(encoding="utf-8"))
    meta["instrument"] = {"name": "DOGE", "szDecimals": 0, "maxLeverage": 10}
    (bundle / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert main(["--data-root", str(data), "nautilus", "run", "--export", "doge"]) == 0
    assert len(phase2) == 1
    capsys.readouterr()


@pytest.mark.parametrize(("ok", "code"), [(True, 0), (False, 1)])
def test_nautilus_check_exit_code_follows_the_report(
    ok: bool,
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}

    def fake(_path: Path, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"ok": ok, "nautilus_run_supported": ok}

    monkeypatch.setattr("hypervector.nautilus.config_stub.phase2_check_report", fake)
    bundle = _strict_export(tmp_path, "chk")
    argv = ["--data-root", str(tmp_path), "nautilus", "check", "--export", str(bundle)]
    assert main([*argv, "--no-signal-probe"]) == code
    assert seen["probe_signals"] is False
    assert json.loads(capsys.readouterr().out)["ok"] is ok


# --- paper / live outputs -------------------------------------------------------------------


def test_paper_report_filters_reach_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake(_root: object, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"ok": True, "filters": {"run_id": kwargs.get("run_id")}}

    monkeypatch.setattr("hypervector.commands.paper.report_from_data_root", fake)
    ledger = tmp_path / "paper" / "decisions" / "decisions.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("", encoding="utf-8")
    argv = ["--data-root", str(tmp_path), "paper", "report"]
    assert main([*argv, "--run-id", "r7", "--strategy", "test_sma_cross_long"]) == 0
    assert (seen["run_id"], seen["strategy"]) == ("r7", "test_sma_cross_long")
    assert json.loads(capsys.readouterr().out)["filters"] == {"run_id": "r7"}


def test_paper_report_imports_no_engine(tmp_path: Path) -> None:
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        f"main(['--data-root', {str(tmp_path / 'absent')!r}, 'paper', 'report',"
        f" '--decisions', {str(tmp_path / 'none.jsonl')!r}])\n"
        "heavy = {'pandas', 'numpy', 'vectorbt', 'nautilus_trader'} & set(sys.modules)\n"
        "assert not heavy, sorted(heavy)\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=60,
        cwd=tmp_path,
        capture_output=True,
    )


def test_paper_and_live_results_report_warmup_and_catchup() -> None:
    from hypervector.commands.live import _live_result
    from hypervector.commands.paper import _paper_result

    warmup = {"mode": "cache_merged", "stale": False}
    paper = SimpleNamespace(
        execution_mode="shadow",
        run_id="p1",
        export_dir=Path("e"),
        decisions_path=Path("d"),
        warm_bars=10,
        live_bars=2,
        bars_processed=12,
        fills_count=0,
        stop_reason="max_live_bars",
        warmup_provenance=warmup,
    )
    options = {
        "preferred_fill_model": "l2",
        "max_book_age_ms": 1.0,
        "metalabel_enabled": False,
        "metalabel_mode": "off",
        "metalabel_filter": False,
        "metalabel_min_p": 0.5,
    }
    assert _paper_result(argparse.Namespace(), paper, options)["warmup"] == warmup
    live = SimpleNamespace(
        **{k: v for k, v in vars(paper).items() if k != "warmup_provenance"},
        places_count=0,
        catchup_bars=3,
        cancel_attempted=True,
        cancel_ok=True,
        cancel_error=None,
    )
    report = _live_result(live, SimpleNamespace(max_notional_usd=50.0))
    assert report["catchup_bars"] == 3
    assert report["cancel_scope"] == "owned_resting_orders"


# --- live validate: one JSON document --------------------------------------------------------


@pytest.mark.parametrize(
    ("problems", "book_problems", "code", "verdict"),
    [
        ([], None, 0, "accepted"),
        (["sizing exceeds scope"], None, 1, "runner_refused"),
        ([], ("book at-stop risk exceeds 3%",), 3, "book_level_advisory"),
    ],
)
def test_live_validate_prints_one_json_document(
    problems: list[str],
    book_problems: tuple[str, ...] | None,
    code: int,
    verdict: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import hypervector.operations.cohort_runtime_validation_check as check

    monkeypatch.setattr(check, "check", lambda *_a, **_k: list(problems))
    monkeypatch.setattr(
        check,
        "book_check",
        lambda *_a, **_k: check.BookCheck(5000.0, 4, (), 200.0, 500.0, book_problems or ()),
    )
    argv = ["--config", str(tmp_path / "p.toml")]
    if book_problems is not None:
        argv += ["--equity", "5000"]
    assert check.main(argv) == code
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert (report["verdict"], report["exit_code"]) == (verdict, code)
    assert report["ok"] is (code in (0, 3))
    if book_problems is not None:
        assert report["book"]["problems"] == list(book_problems)


def test_live_validate_loader_refusal_is_json_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import hypervector.operations.cohort_runtime_validation_check as check

    bad = tmp_path / "bad.toml"
    bad.write_text('profile = "x"\n', encoding="utf-8")
    assert check.main(["--config", str(bad)]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert (report["verdict"], report["exit_code"], report["ok"]) == (
        "loader_refused",
        2,
        False,
    )
    assert captured.err.startswith("loader refused: ")


# --- supervisor usage and resume alert --------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["bogus"], "usage: hypervector live supervisor"),
        (["resume", "--bogus"], "usage: hypervector live supervisor resume"),
    ],
)
def test_supervisor_usage_names_the_cli(
    argv: list[str], usage: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["live", "supervisor", *argv])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert usage in err and "__main__" not in err


def test_resume_alert_names_the_checkout_interpreter() -> None:
    from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT
    from hypervector_supervision.cohort_supervisor_runtime import RESUME_HELPER

    assert RESUME_HELPER.startswith(str(REPOSITORY_ROOT / ".venv" / "bin" / "python"))
    assert RESUME_HELPER.endswith(" -m hypervector live supervisor resume")


def test_live_group_help_names_the_resume_path_to_an_armed_start() -> None:
    from hypervector.commands.registry import groups

    text = groups()["groups"]["live"]["help"]
    assert "live supervisor resume --yes" in text


# --- error boundary ---------------------------------------------------------------------------


def test_database_errors_are_technical_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import duckdb

    raised: list[BaseException] = [
        sqlite3.OperationalError("locked"),
        duckdb.IOException("cannot open"),
    ]

    def broken(_args: argparse.Namespace) -> int:
        raise raised.pop(0)

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    for error_type in ("OperationalError", "IOException"):
        assert main(["--data-root", str(tmp_path), "system", "init"]) == 1
        report = json.loads(capsys.readouterr().err)
        assert report["error_type"] == error_type and report["ok"] is False


def test_error_json_carries_exception_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_args: argparse.Namespace) -> int:
        exc = RuntimeError("fetch failed")
        exc.add_note("kept 10 bars")
        raise exc

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    assert main(["--data-root", str(tmp_path), "system", "init"]) == 1
    assert json.loads(capsys.readouterr().err)["notes"] == ["kept 10 bars"]


def test_non_technical_exceptions_still_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_args: argparse.Namespace) -> int:
        raise Boundary

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    with pytest.raises(Boundary):
        main(["--data-root", str(tmp_path), "system", "init"])


# --- export validate ---------------------------------------------------------------------------


def test_export_validate_require_costed_is_opt_in(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _strict_export(tmp_path, "zero", apply_costs=False)
    argv = ["--data-root", str(tmp_path), "export", "validate", "--export", str(bundle)]
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert "warning:" in captured.err and "apply_costs" in captured.err
    assert json.loads(captured.out)["require_costed"] is False
    assert main([*argv, "--require-costed"]) == 1
    assert "apply_costs" in json.loads(capsys.readouterr().err)["error"]


# --- engine defaults --------------------------------------------------------------------------


def test_research_config_defaults_to_the_base_taker_fee() -> None:
    from hypervector.config import ResearchConfig

    assert ResearchConfig().fee_model == "hl_base_taker"


def test_trial_evaluator_passes_the_symbol_only_when_known() -> None:
    import pandas as pd

    from hypervector.strategies.registry import ExecutionProfile, StrategySpec
    from hypervector.sweep.autotune_evaluation import TrialEvaluator
    from hypervector.sweep.costs import resolve_cost_model

    bars = _bars(50)
    flags = pd.Series(False, index=bars.index)
    spec = StrategySpec("fake", "uptrend", {}, lambda df, **_k: (flags, flags, "long"))
    seen: list[dict[str, object]] = []

    def calculate(*_args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs)
        return {"net_pnl": 0.0, "sharpe": 0.0, "trade_count": 0}

    cost = resolve_cost_model("hl_base_taker")
    for symbol in (None, "ETH"):
        evaluator = TrialEvaluator(
            bars, spec, "long", cost, ExecutionProfile(), calculate, symbol=symbol
        )
        evaluator.measure({}, {"mode": "atr", "leverage": 2.0})
    assert "symbol" not in seen[0]
    assert seen[1]["symbol"] == "ETH"


def test_autotune_measures_every_trial_at_the_symbol_venue_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.sweep import autotune

    bars = _bars(180)
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_args, **_kwargs: (bars, summarize_provenance(bars)),
    )
    seen: list[object] = []
    original = autotune.compute_trial_metrics

    def recording(*args: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs.get("symbol"))
        return original(*args, **kwargs)

    monkeypatch.setattr(autotune, "compute_trial_metrics", recording)
    result = autotune.run_optuna_autotune(
        strategy_name="test_sma_cross_long",
        symbol="ETH",
        timeframe="1m",
        lookback_days=30,
        n_trials=2,
        data_root=tmp_path,
        export_best=False,
    )
    assert seen and set(seen) == {"ETH"}
    assert result.best_metrics.get("venue_leverage_cap") == 25.0


def test_help_imports_no_database_or_dataframe_module(tmp_path: Path) -> None:
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        "try:\n"
        "    main(['--help'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "heavy = {'pandas', 'numpy', 'duckdb', 'sqlite3'} & set(sys.modules)\n"
        "assert not heavy, sorted(heavy)\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=30,
        cwd=tmp_path,
        capture_output=True,
    )


def test_installed_candle_cache_records_its_archive_provenance(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    import pandas as pd

    from hypervector.cli_oxa_candle_cache import INSTALL_ORIGIN, install_candle_cache
    from hypervector.data.cache import ParquetCache
    from hypervector.data.pipeline import cache_key

    start = datetime(2026, 7, 1, tzinfo=UTC)
    args = argparse.Namespace(
        data_root=tmp_path,
        symbol="BTC",
        timeframe="1m",
        start=start,
        end=start + timedelta(days=1),
    )
    stamps = pd.date_range(args.start, args.end, freq="1min", inclusive="left")
    source = tmp_path / "candles.parquet"
    pd.DataFrame(
        {
            "timestamp": stamps,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
            "source": "hl",
        }
    ).to_parquet(source, index=False)
    install_candle_cache(args, {"candles_path": str(source)})
    footer = ParquetCache(tmp_path / "cache").load_metadata(cache_key("BTC", "1m", 1))
    assert footer is not None
    assert (footer["origin"], footer["window_start"]) == (
        INSTALL_ORIGIN,
        start.isoformat(),
    )
    assert footer["bundle"] == str(source)
