"""Offline paper session: warm-up + bar loop into ExplicitFillEngine (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.paper.session import (
    PaperSession,
    PaperSessionResult,
    run_paper_session_offline,
)


def _write_strict_export(root: Path, *, strategy: str = "crown_stack_short") -> Path:
    """Minimal strict Phase 1.5 export for offline session tests."""
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="sess01",
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
            "data_provenance": {"sources": {"fixture": 300}},
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
        candidate_id="paper_session_crown",
        strict=True,
    )


def test_offline_session_writes_paper_decisions(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    ohlcv = fixture_ohlcv(n_bars=300, drift=-5.0, wave_period=40)
    result = run_paper_session_offline(
        export_dir=export,
        data_root=tmp_path / "data",
        ohlcv=ohlcv,
        conviction=0.5,
        max_bars=300,
    )
    assert isinstance(result, PaperSessionResult)
    assert result.bars_processed > 0
    assert result.bars_processed == 300
    assert result.export_dir == export.resolve()
    assert result.run_id
    assert result.decisions_path.is_file()
    text = result.decisions_path.read_text(encoding="utf-8")
    assert "execution_mode" in text
    assert "paper" in text
    assert result.fills_count >= 0


def test_offline_session_no_trade_before_two_bars(tmp_path: Path):
    """Warm-up matches actor: no intent/fill path until buffer length >= 2."""
    export = _write_strict_export(tmp_path)
    ohlcv = fixture_ohlcv(n_bars=1, drift=-5.0)
    result = run_paper_session_offline(
        export_dir=export,
        data_root=tmp_path / "data",
        ohlcv=ohlcv,
        max_bars=1,
    )
    assert result.bars_processed == 1
    assert result.fills_count == 0


def test_offline_session_rejects_bad_ohlcv(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    import pandas as pd

    bad = pd.DataFrame({"close": [1.0, 2.0]})
    with pytest.raises(ValueError, match="OHLCV"):
        run_paper_session_offline(
            export_dir=export,
            data_root=tmp_path / "data",
            ohlcv=bad,
        )


def test_offline_session_missing_export(tmp_path: Path):
    ohlcv = fixture_ohlcv(n_bars=5)
    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        run_paper_session_offline(
            export_dir=tmp_path / "missing_export",
            data_root=tmp_path / "data",
            ohlcv=ohlcv,
        )


def test_session_applies_funding_on_open_long(tmp_path: Path):
    """Open long + non-zero hourly rate → on_bar writes signed funding decision."""
    export = _write_strict_export(tmp_path)
    rate = 0.0001
    mark = 50_000.0
    qty = 1.0
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=rate,
        enable_funding_refresh=False,
    )
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=qty,
        mark_px=mark,
    )
    bar = {
        "timestamp": pd.Timestamp("2026-07-22T00:01:00Z"),
        "open": mark,
        "high": mark,
        "low": mark,
        "close": mark,
        "volume": 1.0,
    }
    session.on_bar(bar)

    lines = [
        json.loads(line)
        for line in session.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    funding_rows = [r for r in lines if r.get("action") == "funding"]
    assert len(funding_rows) == 1
    fre = funding_rows[0]
    assert fre["funding_payment_usd"] == pytest.approx(qty * mark * rate)
    assert fre["funding_payment_usd"] > 0  # long pays when rate > 0
    assert fre["funding_rate_hourly"] == pytest.approx(rate)
    assert fre["side"] == "buy"
    assert session.engine.position.qty == qty


def test_session_funding_refresh_disabled_offline(tmp_path: Path, monkeypatch):
    """enable_funding_refresh=False must never hit CostProvider.refresh_funding."""
    export = _write_strict_export(tmp_path)
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path / "data",
        funding_rate_hourly=0.0001,
        enable_funding_refresh=False,
    )

    def _boom(*_a, **_k):
        raise AssertionError("refresh_funding must not be called offline")

    monkeypatch.setattr(session.cost_provider, "refresh_funding", _boom)
    session.engine.apply_market_fill(
        feed_ts="t0",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=50_000.0,
    )
    session.on_bar(
        {
            "timestamp": pd.Timestamp("2026-07-22T00:01:00Z"),
            "open": 50_000.0,
            "high": 50_000.0,
            "low": 50_000.0,
            "close": 50_000.0,
            "volume": 1.0,
        }
    )
    assert session.maybe_refresh_funding() is None
