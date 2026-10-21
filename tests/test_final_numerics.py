"""Numerics review findings, one regression test (or more) each.

1. ``pipeline run --search tune --no-network`` never re-fetches history: the
   tune stage reads exactly the window the data stage pinned.
2. The pipeline parity block labels holdout-only autotune metrics with the
   holdout window and prefers a full-window VectorBT re-measure.
3. Funding accrues per bar into real equity, so Sharpe, drawdown, min equity,
   equity depletion and win/loss counts all include it, not only ``net_pnl``.
4. Holdout measurement keeps the full-history ATR warmup for stop distances.
5. ``backtest run`` reports ``max_drawdown_pct`` in percent and a real
   ``profit_factor``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from hypervector.strategies.registry import ExecutionProfile
from hypervector.cli import main
from hypervector.data.cache import ParquetCache
from hypervector.data.sources import fixture_ohlcv


# --- 1. the pipeline tune stage never fetches ---------------------------------------------


def _stale_legacy_cache(data: Path, *, bars: int = 500) -> Path:
    """A metadata-less (legacy) cache whose last bar is years old: stale and partial."""
    frame = fixture_ohlcv(
        n_bars=bars, freq="1h", drift=5.0, wave_period=30, source="hl"
    )
    return ParquetCache(data / "cache").save("BTC_1h_30d", frame)


def test_pipeline_tune_no_network_reads_the_pinned_cache_and_never_fetches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    cache = _stale_legacy_cache(data)
    before = cache.read_bytes()
    fetches: list[str] = []

    def no_fetch(*_args: object, **_kwargs: object) -> None:
        fetches.append("fetch")
        raise RuntimeError("NETWORK FETCH ATTEMPTED")

    monkeypatch.setattr("hypervector.data.pipeline._fetch", no_fetch)
    argv = [
        "--data-root",
        str(data),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        "--symbol",
        "BTC",
        "--timeframe",
        "1h",
        "--lookback-days",
        "30",
        "--search",
        "tune",
        "--no-network",
        "--no-nautilus",
        "--n-trials",
        "2",
    ]
    code = main(argv)
    manifest = json.loads(capsys.readouterr().out)
    stages = {stage["stage"]: stage for stage in manifest["stages"]}
    assert fetches == []
    assert code == 0, stages["search"]
    assert stages["search"]["status"] == "ok"
    assert cache.read_bytes() == before  # the pinned window was never rewritten
    assert "--pin-cache" in stages["search"]["argv"]
    export_meta = json.loads(
        (Path(manifest["export_dir"]) / "meta.json").read_text(encoding="utf-8")
    )
    assert export_meta["data_provenance"]["bar_count"] == manifest["window"]["bars"]


def test_run_autotune_offline_never_fetches_on_a_cache_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.sweep import autotune

    monkeypatch.setattr(
        "hypervector.data.pipeline._fetch",
        lambda *_a, **_k: pytest.fail("offline autotune reached the network"),
    )
    with pytest.raises(FileNotFoundError, match="offline history cache missing"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name="test_sma_cross_long",
            n_trials=1,
            allow_network=False,
        )
    with pytest.raises(ValueError, match="needs the network"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name="test_sma_cross_long",
            n_trials=1,
            allow_network=False,
            force_refresh=True,
        )


# --- 2. parity compares like with like ----------------------------------------------------


def _holdout_report(*, full_metrics: dict[str, object] | None) -> dict[str, Any]:
    """An export report shaped like an autotune bundle with a 70/30 holdout."""
    evaluation: dict[str, object] = {
        "evaluation_window": "holdout",
        "train_window": {
            "first_bar_utc": "2024-01-01T00:00:00+00:00",
            "last_bar_utc": "2024-01-12T19:00:00+00:00",
            "bar_count": 284,
        },
        "holdout_window": {
            "first_bar_utc": "2024-01-12T20:00:00+00:00",
            "last_bar_utc": "2024-01-17T23:00:00+00:00",
            "bar_count": 124,
        },
        "full_window": {
            "first_bar_utc": "2024-01-01T00:00:00+00:00",
            "last_bar_utc": "2024-01-17T23:00:00+00:00",
            "bar_count": 408,
        },
    }
    if full_metrics is not None:
        evaluation["full_window_metrics"] = full_metrics
    return {
        "meta": {
            "symbol": "BTC",
            "timeframe": "1h",
            "lookback_days": 30,
            "data_provenance": {
                "bar_count": 408,
                "start": "2024-01-01T00:00:00+00:00",
                "end": "2024-01-17T23:00:00+00:00",
            },
            "evaluation": evaluation,
        },
        "metrics": {"net_pnl": -40.0, "trade_count": 3, "evaluation_window": "holdout"},
    }


def _pinned_window() -> dict[str, object]:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "lookback_days": 30,
        "start": "2024-01-01 00:00:00+00:00",
        "end": "2024-01-17 23:00:00+00:00",
        "bars": 408,
    }


def _nautilus_window(bars: int = 408) -> dict[str, object]:
    return {
        "pnl": -90.0,
        "orders": 20,
        "trades": 10,
        "window": {
            "symbol": "BTC",
            "timeframe": "1h",
            "lookback_days": 30,
            "bars": bars,
        },
    }


def test_parity_labels_holdout_only_export_metrics_with_the_holdout_window() -> None:
    from hypervector.commands.pipeline import parity_block

    parity = parity_block(
        pinned=_pinned_window(),
        export_report=_holdout_report(full_metrics=None),
        nautilus=_nautilus_window(),
    )
    vectorbt = parity["vectorbt"]
    assert vectorbt["evaluation_window"] == "holdout"
    assert vectorbt["net_pnl"] == -40.0 and vectorbt["trades"] == 3
    assert vectorbt["window"]["bars"] == 124
    assert vectorbt["window"]["start"] == "2024-01-12T20:00:00+00:00"
    # VectorBT scored 124 holdout bars, Nautilus replayed all 408: not like for like.
    assert parity["window_mismatch"] is True
    assert "bars" in parity["window_mismatch_fields"]


def test_parity_prefers_the_full_window_re_measure_when_the_bundle_records_it() -> None:
    from hypervector.commands.pipeline import parity_block

    full = {"net_pnl": -88.0, "trade_count": 10}
    parity = parity_block(
        pinned=_pinned_window(),
        export_report=_holdout_report(full_metrics=full),
        nautilus=_nautilus_window(),
    )
    vectorbt = parity["vectorbt"]
    assert vectorbt["source"] == "full-window re-measure"
    assert vectorbt["evaluation_window"] == "full"
    assert vectorbt["net_pnl"] == -88.0 and vectorbt["trades"] == 10
    assert vectorbt["window"]["bars"] == 408
    assert parity["window_mismatch"] is False
    assert {"start", "end", "bars"} <= set(parity["compared_fields"])
    exported = parity["vectorbt_export"]
    assert exported["evaluation_window"] == "holdout"
    assert exported["net_pnl"] == -40.0 and exported["window"]["bars"] == 124


def test_parity_compares_window_start_and_end_not_only_the_bar_count() -> None:
    from hypervector.commands.pipeline import parity_block

    report = _holdout_report(full_metrics={"net_pnl": -88.0, "trade_count": 10})
    # Same bar count, but the search measured a later (re-fetched) window.
    report["meta"]["evaluation"]["full_window"] = {
        "first_bar_utc": "2024-03-01T00:00:00+00:00",
        "last_bar_utc": "2024-03-17T23:00:00+00:00",
        "bar_count": 408,
    }
    parity = parity_block(
        pinned=_pinned_window(), export_report=report, nautilus=_nautilus_window()
    )
    assert parity["window_mismatch"] is True
    assert {"start", "end"} <= set(parity["window_mismatch_fields"])


def test_parity_keeps_full_window_export_metrics_as_they_are() -> None:
    """A sweep (or train_fraction=1.0) bundle reports full-window metrics already."""
    from hypervector.commands.pipeline import parity_block

    report = _holdout_report(full_metrics=None)
    report["metrics"] = {"net_pnl": -70.0, "trade_count": 9}
    del report["meta"]["evaluation"]
    parity = parity_block(
        pinned=_pinned_window(), export_report=report, nautilus=_nautilus_window()
    )
    assert parity["vectorbt"]["source"] == "export metrics"
    assert parity["vectorbt"]["window"]["bars"] == 408
    assert parity["window_mismatch"] is False
    assert "vectorbt_export" not in parity


def test_pipeline_tune_parity_compares_the_full_window_re_measure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End to end: a real tune (70/30 holdout) next to a Nautilus replay of every bar."""
    from types import SimpleNamespace

    data = tmp_path / "data"
    _stale_legacy_cache(data, bars=500)
    monkeypatch.setattr(
        "hypervector.data.pipeline._fetch",
        lambda *_a, **_k: pytest.fail("the pipeline reached the network"),
    )

    def replay(**kwargs: Any) -> SimpleNamespace:
        report = Path(kwargs["data_root"]) / "nautilus" / "n1" / "summary.json"
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps({"run_id": "n1", "bars": 500, "trade_count": 7}))
        return SimpleNamespace(pnl=-12.5, orders_count=14, report_path=report)

    monkeypatch.setattr(
        "hypervector.nautilus.config_stub.phase2_check_report",
        lambda *_a, **_k: {"ok": True},
    )
    monkeypatch.setattr("hypervector.nautilus.runner.run_phase2_backtest", replay)
    argv = [
        "--data-root",
        str(data),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        "--timeframe",
        "1h",
        "--lookback-days",
        "30",
        "--no-network",
        "--n-trials",
        "3",
    ]
    assert main(argv) == 0
    manifest = json.loads(capsys.readouterr().out)
    parity = manifest["parity"]
    meta = json.loads((Path(manifest["export_dir"]) / "meta.json").read_text())
    holdout_bars = meta["evaluation"]["holdout_window"]["bar_count"]
    assert 0 < holdout_bars < 500
    assert parity["vectorbt"]["source"] == "full-window re-measure"
    assert parity["vectorbt"]["window"]["bars"] == 500
    assert parity["vectorbt_export"]["evaluation_window"] == "holdout"
    assert parity["vectorbt_export"]["window"]["bars"] == holdout_bars
    assert parity["window_mismatch"] is False
    assert {"bars", "start", "end"} <= set(parity["compared_fields"])


def _offline_autotune_history(
    monkeypatch: pytest.MonkeyPatch, n_bars: int = 400
) -> pd.DataFrame:
    from hypervector.data.provenance import summarize_provenance
    from hypervector.sweep import autotune

    bars = fixture_ohlcv(n_bars=n_bars, drift=5.0, wave_period=30, source="hl")
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda _root, **_kwargs: (bars, summarize_provenance(bars)),
    )
    return bars


def test_autotune_records_the_selected_trial_re_measured_on_every_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy
    from hypervector.sweep import autotune
    from hypervector.sweep.autotune_evaluation import TrialEvaluator
    from hypervector.sweep.costs import resolve_cost_model
    from hypervector.sweep.metrics import compute_trial_metrics

    bars = _offline_autotune_history(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path, n_trials=3, strategy_name="test_sma_cross_long"
    )
    assert result.export_dir is not None
    meta = json.loads((Path(result.export_dir) / "meta.json").read_text())
    evaluation = meta["evaluation"]
    assert evaluation["evaluation_window"] == "holdout"
    assert evaluation["full_window"]["bar_count"] == len(bars)
    full = evaluation["full_window_metrics"]
    register_all_strategies()
    evaluator = TrialEvaluator(
        bars,
        get_strategy("test_sma_cross_long"),
        None,
        resolve_cost_model(result.fee_model_used),
        ExecutionProfile(),
        compute_trial_metrics,
        symbol="BTC",
    )
    expected, _ = evaluator.measure(result.best_params, result.best_exit_cfg)
    assert full["net_pnl"] == pytest.approx(expected["net_pnl"])
    assert full["trade_count"] == expected["trade_count"]
    board = json.loads(Path(result.board_path).read_text())
    assert board["best_full_window_metrics"]["net_pnl"] == pytest.approx(
        expected["net_pnl"]
    )


def test_autotune_in_sample_mode_needs_no_separate_full_window_measure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.sweep import autotune

    _offline_autotune_history(monkeypatch)
    result = autotune.run_autotune(
        data_root=tmp_path,
        n_trials=2,
        strategy_name="test_sma_cross_long",
        train_fraction=1.0,
    )
    assert result.export_dir is not None
    meta = json.loads((Path(result.export_dir) / "meta.json").read_text())
    assert meta["evaluation"]["evaluation_window"] == "full_window_in_sample"
    assert meta["evaluation"]["full_window_metrics"] is None


# --- 3. funding accrues into real equity --------------------------------------------------

_FUNDING_RATE_1H = 1.25e-5


def _hourly_bars(n_bars: int, *, end_price: float = 100.0) -> pd.DataFrame:
    stamps = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz="UTC")
    close = np.linspace(100.0, end_price, n_bars)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
        }
    )


def _held_long(
    bars: pd.DataFrame,
    *,
    leverage: float = 5.0,
    entry: int = 0,
    exit_at: int | None = None,
    funding: float = _FUNDING_RATE_1H,
) -> dict[str, Any]:
    """One long held at ``leverage`` x initial equity, zero fees and slippage."""
    from hypervector.sweep.costs import CostModel
    from hypervector.sweep.metrics import compute_trial_metrics

    entries = pd.Series(False, index=bars.index)
    entries.iloc[entry] = True
    exits = pd.Series(False, index=bars.index)
    if exit_at is not None:
        exits.iloc[exit_at] = True
    cost = CostModel(
        taker_fee=0.0, maker_fee=0.0, slippage_bps=0.0, funding_rate_1h=funding
    )
    return compute_trial_metrics(
        bars["close"],
        entries,
        exits,
        df=bars,
        cost=cost,
        fixed_notional_fraction=leverage,
        strategy_managed_exits=True,
        symbol="BTC",
    )


def test_funding_drag_reaches_drawdown_sharpe_and_min_equity() -> None:
    bars = _hourly_bars(90 * 24)
    metrics = _held_long(bars)
    held_hours = len(bars) - 1
    expected = 10_000.0 * 5.0 * _FUNDING_RATE_1H * held_hours
    assert metrics["funding_cost"] == pytest.approx(expected)
    assert metrics["net_pnl"] == pytest.approx(-expected)
    final_equity = 10_000.0 - expected
    assert metrics["min_equity"] == pytest.approx(final_equity)
    assert metrics["max_drawdown"] == pytest.approx(final_equity / 10_000.0 - 1.0)
    assert metrics["sharpe"] < 0.0
    assert (metrics["wins"], metrics["losses"]) == (0, 1)
    assert metrics["equity_depleted"] is False


def test_a_trade_that_loses_net_of_funding_is_a_loss() -> None:
    bars = _hourly_bars(90 * 24, end_price=100.5)
    without = _held_long(bars, funding=0.0)
    metrics = _held_long(bars)
    assert without["net_pnl"] == pytest.approx(250.0)
    assert (without["wins"], without["losses"]) == (1, 0)
    assert metrics["net_pnl"] == pytest.approx(250.0 - metrics["funding_cost"])
    assert metrics["net_pnl"] < 0.0
    assert (metrics["wins"], metrics["losses"]) == (0, 1)
    assert metrics["min_equity"] == pytest.approx(
        10_000.0 + metrics["net_pnl"], rel=1e-6
    )
    assert metrics["sharpe"] < without["sharpe"]


def test_funding_accrues_over_the_held_bars_only() -> None:
    """A closed trade pays from entry to exit; equity is flat before and after."""
    bars = _hourly_bars(400)
    metrics = _held_long(bars, entry=100, exit_at=300)
    expected = 10_000.0 * 5.0 * _FUNDING_RATE_1H * 200
    assert metrics["funding_cost"] == pytest.approx(expected)
    assert metrics["net_pnl"] == pytest.approx(-expected)
    assert metrics["min_equity"] == pytest.approx(10_000.0 - expected)
    assert metrics["max_drawdown"] == pytest.approx(-expected / 10_000.0)


def test_funding_can_deplete_the_account() -> None:
    bars = _hourly_bars(90 * 24)
    metrics = _held_long(bars, leverage=40.0)
    assert metrics["funding_cost"] > 10_000.0
    assert metrics["min_equity"] == pytest.approx(10_000.0 + metrics["net_pnl"])
    assert metrics["min_equity"] < 0.0
    assert metrics["equity_depleted"] is True
    assert metrics["max_drawdown"] == -1.0


# --- 4. holdout stops keep the full-history ATR warmup ------------------------------------

_CUT = 1400
_ENTRY = _CUT + 2


def _single_entry_spec(entry: int) -> Any:
    from hypervector.strategies.registry import StrategySpec

    def build(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, str]:
        entries = pd.Series(False, index=df.index)
        if entry < len(df):
            entries.iloc[entry] = True
        return entries, pd.Series(False, index=df.index), "long"

    return StrategySpec(
        name="final_numerics_single_entry",
        role="uptrend",
        param_grid={},
        build_signals=build,
    )


@pytest.mark.parametrize("mode", ["atr", "trail"])
def test_holdout_stop_distance_matches_a_full_history_run(mode: str) -> None:
    from hypervector.sweep.autotune_evaluation import TrialEvaluator
    from hypervector.sweep.costs import resolve_cost_model
    from hypervector.sweep.exits import ExitConfig, stop_distance_frac
    from hypervector.sweep.metrics import compute_trial_metrics

    bars = fixture_ohlcv(n_bars=2000, drift=0.5, wave_period=90, source="hl")
    exits = {
        "mode": mode,
        "sl_pct": 0.01,
        "sl_atr_mult": 2.0,
        "trail_atr_mult": 2.0,
        "rr": 2.0,
        "leverage": 5.0,
    }
    evaluator = TrialEvaluator(
        bars,
        _single_entry_spec(_ENTRY),
        None,
        resolve_cost_model("hl_base_taker"),
        ExecutionProfile(),
        compute_trial_metrics,
        symbol="BTC",
    )
    holdout, _ = evaluator.measure({}, exits, evaluation_start=_CUT)
    full, _ = evaluator.measure({}, exits)
    assert holdout["trade_count"] == full["trade_count"] == 1
    # The full-history ATR stop is far tighter than the sl_pct cold-start fallback.
    config = ExitConfig(mode=mode, sl_pct=0.01, sl_atr_mult=2.0, trail_atr_mult=2.0)
    warm = float(stop_distance_frac(bars, config).iloc[_ENTRY])
    assert warm < 0.005
    # Same stop at the entry: same size, same exit, same P&L as a full-history run.
    assert holdout["max_position_leverage"] == pytest.approx(
        full["max_position_leverage"]
    )
    assert holdout["effective_risk_pct"] == pytest.approx(full["effective_risk_pct"])
    assert holdout["net_pnl"] == pytest.approx(full["net_pnl"])


def test_compute_trial_metrics_accepts_a_precomputed_stop_distance() -> None:
    from hypervector.sweep.exits import ExitConfig
    from hypervector.sweep.metrics import compute_trial_metrics
    from hypervector.sweep.sizing import RiskConfig

    bars = fixture_ohlcv(n_bars=300, drift=0.5, wave_period=90, source="hl")
    entries = pd.Series(False, index=bars.index)
    entries.iloc[5] = True
    exits = pd.Series(False, index=bars.index)
    config = ExitConfig(mode="atr", sl_pct=0.01, sl_atr_mult=2.0, rr=2.0)
    common: dict[str, Any] = {
        "df": bars,
        "exit_cfg": config,
        "risk_cfg": RiskConfig(max_size_frac=20.0),
        "symbol": "BTC",
    }
    cold = compute_trial_metrics(bars["close"], entries, exits, **common)
    stop = pd.Series(0.002, index=bars.index)
    warm = compute_trial_metrics(
        bars["close"], entries, exits, stop_distance=stop, **common
    )
    assert warm["effective_risk_pct"] == pytest.approx(
        warm["max_position_leverage"] * 0.002 * 100.0, rel=1e-6
    )
    assert warm["max_position_leverage"] != pytest.approx(cold["max_position_leverage"])


# --- 5. backtest report units -------------------------------------------------------------


def _report_args() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        strategy="test_sma_cross_long",
        symbol="BTC",
        timeframe="15m",
        lookback=180,
        leverage=3.0,
        initial_cash=10_000.0,
        fee_model="hl_base_taker",
        book_gate=False,
    )


def test_backtest_report_prints_drawdown_in_percent() -> None:
    from hypervector.commands.backtest import _backtest_report

    metrics = {
        "net_pnl": -3784.0,
        "total_return_pct": -37.84,
        "sharpe": -1.2,
        "max_drawdown": -0.3729,
        "trade_count": 96,
        "wins": 31,
        "losses": 65,
        "win_pct": 32.3,
        "profit_factor": 0.61234,
    }
    report = _backtest_report(_report_args(), metrics)["metrics"]
    assert report["max_drawdown_pct"] == -37.29
    assert report["total_return_pct"] == -37.84
    assert report["profit_factor"] == 0.61


def test_trial_metrics_report_profit_factor_net_of_funding() -> None:
    from hypervector.sweep.costs import CostModel
    from hypervector.sweep.metrics import compute_trial_metrics

    bars = fixture_ohlcv(n_bars=400, drift=0.5, wave_period=60, source="hl")
    entries = pd.Series(False, index=bars.index)
    exits = pd.Series(False, index=bars.index)
    # Trough to peak (win), peak to trough (loss), trough to peak (win).
    entries.iloc[[45, 135, 225]] = True
    exits.iloc[[75, 165, 255]] = True
    metrics = compute_trial_metrics(
        bars["close"],
        entries,
        exits,
        df=bars,
        cost=CostModel(funding_rate_1h=0.0),
        strategy_managed_exits=True,
        fixed_notional_fraction=2.0,
        symbol="BTC",
    )
    assert metrics["trade_count"] == 3
    assert metrics["wins"] >= 1 and metrics["losses"] >= 1
    pnls = _trade_pnls(bars, entries, exits)
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    assert metrics["profit_factor"] == pytest.approx(gross_profit / gross_loss)

    losing = _held_long(_hourly_bars(90 * 24))  # one trade, lost to funding
    assert losing["profit_factor"] == 0.0
    idle = _held_long(_hourly_bars(30), entry=29, funding=0.0)  # flat, no loss
    assert idle["profit_factor"] is None


def _trade_pnls(
    bars: pd.DataFrame, entries: pd.Series, exits: pd.Series
) -> list[float]:
    """Per-trade P&L recomputed from the fills VectorBT reports."""
    import vectorbt as vbt

    from hypervector.sweep.costs import CostModel

    cost = CostModel(funding_rate_1h=0.0)
    close = bars["close"].astype(float)
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        init_cash=1e9,
        size=20_000.0,
        size_type="value",
        fees=cost.fees,
        slippage=cost.slippage,
        open=bars["open"].to_numpy(),
        high=bars["high"].to_numpy(),
        low=bars["low"].to_numpy(),
    )
    return [float(p) for p in pf.trades.records_arr["pnl"]]
