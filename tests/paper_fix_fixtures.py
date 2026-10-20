"""Shared offline fixtures for the paper-engine regression tests (no network)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from hypervector.export.phase2 import export_candidate
from hypervector.strategies.hypervelocity_profile import (
    HypervelocityProfile,
    load_hypervelocity_profile,
)

FAITHFUL_PROFILE = Path(__file__).resolve().parent / "fixtures" / "profiles" / (
    "hypervelocity_shadow.toml"
)
_FAITHFUL_EXPORT = "data/exports/uptrend_hypervelocity_1m_scalper_long_784548f1"


def write_strict_export(
    root: Path,
    *,
    strategy: str = "crown_stack_short",
    timeframe: str = "1m",
    run_id: str = "paperfix1",
) -> Path:
    """Write a minimal strict export for offline paper sessions."""
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id=run_id,
        meta={
            "symbol": "BTC",
            "timeframe": timeframe,
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
        candidate_id="paper_fix",
        strict=True,
    )


def faithful_profile(tmp_path: Path, export: Path) -> HypervelocityProfile:
    """Load the faithful profile pointed at a temporary export, models off."""
    text = FAITHFUL_PROFILE.read_text(encoding="utf-8")
    path = tmp_path / "profile.toml"
    path.write_text(text.replace(_FAITHFUL_EXPORT, str(export)), encoding="utf-8")
    return replace(load_hypervelocity_profile(path), metalabel_mode="off")


def hl_bars(start: str, count: int, *, step: str = "1min", close: float = 100.0):
    """Return ``count`` contiguous Hyperliquid-sourced OHLCV bars."""
    stamps = pd.date_range(pd.Timestamp(start), periods=count, freq=step)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": [close] * count,
            "high": [close + 0.5] * count,
            "low": [close - 0.5] * count,
            "close": [close] * count,
            "volume": [1.0] * count,
            "source": ["hl"] * count,
        }
    )
