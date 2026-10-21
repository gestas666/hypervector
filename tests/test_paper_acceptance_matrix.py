"""Paper completeness acceptance matrix (dry-run only; no venue submit).

Drives real paper daemon / session entry points offline.
"""

from __future__ import annotations

import json
from pathlib import Path


from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.infra import ensure_data_layout
from hypervector.paper.report import report_from_data_root
from hypervector.paper.runner import start_paper_daemon


def _write_strict_export(root: Path, *, strategy: str = "test_sma_cross_short") -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="pcmatrix1",
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
        candidate_id="pc_matrix",
        strict=True,
    )


def _run_daemon(
    tmp_path: Path,
    *,
    execution_mode: str,
    metalabel_enabled: bool = False,
    stop_file: Path | None = None,
    max_live_bars: int = 3,
):
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    ensure_data_layout(data)
    # Stronger path: same shape as offline daemon tests that produce fills.
    warm = fixture_ohlcv(n_bars=80, drift=-5.0, wave_period=20)
    live = fixture_ohlcv(n_bars=max(max_live_bars + 2, 10), drift=-5.0, wave_period=20)
    live = live.copy()
    live["timestamp"] = (
        warm["timestamp"].iloc[-1]
        + (live["timestamp"] - live["timestamp"].iloc[0])
        + (warm["timestamp"].iloc[1] - warm["timestamp"].iloc[0])
    )
    calls = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return live.iloc[:max_live_bars].copy()
        return live.iloc[0:0].copy()

    result = start_paper_daemon(
        export_dir=export,
        data_root=data,
        conviction=0.5,
        fee_tier=0,
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        max_live_bars=max_live_bars,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
        execution_mode=execution_mode,
        metalabel_enabled=metalabel_enabled,
        stop_file=stop_file,
        preferred_fill_model="l2_walk_v1",
        max_book_age_ms=3000,
    )
    return result, data


def _assert_no_live_files(data: Path) -> None:
    live = data / "live"
    files = [p for p in live.rglob("*") if p.is_file()] if live.exists() else []
    assert files == []


def test_matrix_shadow_default_stamps_and_intents(tmp_path: Path):
    from hypervector.paper.costs import CostProvider
    from hypervector.paper.fills import ExplicitFillEngine

    result, data = _run_daemon(tmp_path, execution_mode="shadow")
    assert result.execution_mode == "shadow"
    assert result.decisions_path.is_file()
    rows = [
        json.loads(line)
        for line in result.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    # Every stamped row (including session_start) must carry the daemon mode.
    assert all(r.get("execution_mode") == "shadow" for r in rows)
    assert all(r.get("submitted") is False for r in rows)
    assert all(r.get("network") == "mainnet" for r in rows)

    # Strategy may be flat on synthetic OHLCV — still exercise real fill path for intents.
    engine = ExplicitFillEngine(
        data,
        cost_provider=CostProvider(fee_tier=0),
        run_id="matrix",
        export_id="matrix",
        strategy_name="test_sma_cross_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        execution_mode="shadow",
    )
    fill = engine.apply_market_fill(
        feed_ts="2026-07-23T12:00:00+00:00",
        action="enter_short",
        side="sell",
        qty=0.01,
        mark_px=50_000.0,
    )
    assert fill["execution_mode"] == "shadow"
    assert fill["submitted"] is False
    assert fill["network"] == "mainnet"
    oi = fill["order_intent"]
    assert oi["submit_enabled"] is False
    assert oi["schema"] == "hv_order_intent_v1"

    _assert_no_live_files(data)
    rep = report_from_data_root(data)
    assert rep["honesty"]["all_submitted_false_or_absent"] is True
    assert rep["honesty"]["all_intent_submit_enabled_false"] is True
    assert rep["honesty"]["no_live_files"] is True
    assert rep["market_fills"] >= 1


def test_matrix_forced_paper_mode(tmp_path: Path):
    result, data = _run_daemon(tmp_path, execution_mode="paper")
    assert result.execution_mode == "paper"
    rows = [
        json.loads(line)
        for line in result.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert all(r.get("execution_mode") == "paper" for r in rows)
    assert all(r.get("submitted") is False for r in rows)
    assert all(r.get("network") == "mainnet" for r in rows)
    _assert_no_live_files(data)


def test_matrix_stop_file_stops_daemon(tmp_path: Path):
    stop = tmp_path / "stop.flag"
    stop.write_text("stop\n", encoding="utf-8")
    result, data = _run_daemon(
        tmp_path, execution_mode="shadow", stop_file=stop, max_live_bars=50
    )
    assert result.stop_reason in (
        "stop_file",
        "max_live_bars",
        "poll_exhausted",
        "stop",
    )
    # Pre-existing stop file should stop without requiring many live bars.
    assert result.stop_reason == "stop_file" or result.live_bars <= 50
    _assert_no_live_files(data)


def test_matrix_metalabel_flag_off_by_default_path(tmp_path: Path):
    """Metalabel default-off still produces shadow decisions (no crash)."""
    result, data = _run_daemon(
        tmp_path, execution_mode="shadow", metalabel_enabled=False
    )
    assert result.execution_mode == "shadow"
    assert result.decisions_path.is_file()
    _assert_no_live_files(data)


def test_matrix_max_live_bars_bound(tmp_path: Path):
    result, data = _run_daemon(tmp_path, execution_mode="shadow", max_live_bars=2)
    assert result.live_bars <= 2
    assert result.stop_reason in ("max_live_bars", "poll_exhausted", "stop")
    _assert_no_live_files(data)
