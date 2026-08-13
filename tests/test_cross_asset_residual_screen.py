"""Complete-cell tests for the cross-asset residual development screen."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    declared_residual_pairs,
)
from hypervector.research.cross_asset_residual_screen import (
    build_residual_exit_surface,
    build_residual_screen,
)


def _asset_minutes(symbol: str, phase: float) -> pd.DataFrame:
    rows = 600
    times = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    trend = 4.0 + np.linspace(0.0, 0.03, rows)
    wave = 0.004 * np.sin(np.arange(rows) / 31.0 + phase)
    wave[360:365] += 0.04 * (1.0 if phase < 2.0 else -1.0)
    close = np.exp(trend + wave)
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close * 1.0005,
            "low": close * 0.9995,
            "close": close,
            "volume": 10.0,
            "source": "hl",
            "funding_rate": 0.0,
            "symbol": symbol,
        }
    )


def test_screen_retains_all_six_pair_cells_and_report_only_contract() -> None:
    """Zero-trade and losing cells must remain visible in one immutable result."""
    frames = {
        symbol: _asset_minutes(symbol, phase)
        for symbol, phase in zip(
            ("BTC", "ETH", "SOL", "HYPE"),
            (0.0, 1.0, 2.0, 3.0),
            strict=True,
        )
    }
    config = CrossAssetResidualConfig(
        lookback_bars=30,
        zscore_window_bars=20,
        refit_interval_bars=10,
        minimum_abs_error_correction_t=0.0,
        maximum_hold_bars=12,
    )
    artifact, trades = build_residual_screen(
        minute_frames=frames,
        config=config,
        run_id="fixture",
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-01-01T10:00:00Z"),
        source_identity={symbol: {"sha256": symbol.lower()} for symbol in frames},
    )

    observed = tuple(
        (cell["left_symbol"], cell["right_symbol"]) for cell in artifact["cells"]
    )
    assert observed == declared_residual_pairs()
    assert artifact["trial_count"] == 6
    assert artifact["schema_version"] == "cross_asset_residual_development_v2"
    assert artifact["report_only"] is True
    assert artifact["execution_authority"] == "none"
    assert artifact["independent_pair_accounts"] is True
    assert artifact["start_utc"] == "2026-01-01T00:00:00+00:00"
    assert artifact["end_utc"] == "2026-01-01T10:00:00+00:00"
    assert set(artifact["source_identity"]) == {"BTC", "ETH", "SOL", "HYPE"}
    assert len(artifact["gap_audits"]) == 6
    assert set(trades.columns).issuperset(
        {
            "left_symbol",
            "right_symbol",
            "direction",
            "fees_usd",
            "exit_reason",
            "report_only",
            "execution_authority",
        }
    )
    assert trades["report_only"].all()
    assert trades["execution_authority"].eq("none").all()


def test_exit_surface_reuses_one_signal_contract_across_global_variants() -> None:
    """Exit attribution may vary hold/stop only while retaining every pair."""
    frames = {
        symbol: _asset_minutes(symbol, phase)
        for symbol, phase in zip(
            ("BTC", "ETH", "SOL", "HYPE"),
            (0.0, 1.0, 2.0, 3.0),
            strict=True,
        )
    }
    base = CrossAssetResidualConfig(
        lookback_bars=30,
        zscore_window_bars=20,
        refit_interval_bars=10,
        minimum_abs_error_correction_t=0.0,
        maximum_hold_bars=12,
    )
    variants = (
        ("stop4_hold12", base),
        ("stop3_hold6", replace(base, stop_z=3.0, maximum_hold_bars=6)),
    )
    artifact, trades = build_residual_exit_surface(
        minute_frames=frames,
        variants=variants,
        run_id="surface",
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-01-01T10:00:00Z"),
        source_identity={symbol: {"sha256": symbol.lower()} for symbol in frames},
    )

    assert artifact["trial_count"] == 12
    assert artifact["schema_version"] == "cross_asset_residual_exit_surface_v2"
    assert len(artifact["gap_audits"]) == 12
    assert {cell["trial_id"] for cell in artifact["cells"]} == {
        "stop4_hold12",
        "stop3_hold6",
    }
    grouped: dict[tuple[str, str], set[int]] = {}
    for cell in artifact["cells"]:
        key = (cell["left_symbol"], cell["right_symbol"])
        grouped.setdefault(key, set()).add(cell["signal_count"])
    assert all(len(counts) == 1 for counts in grouped.values())
    assert "trial_id" in trades.columns
    assert trades["report_only"].all()
    assert trades["execution_authority"].eq("none").all()
