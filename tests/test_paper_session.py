"""Offline paper session: warm-up + bar loop into ExplicitFillEngine (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.paper.session import PaperSessionResult, run_paper_session_offline


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
