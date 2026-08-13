"""Tests for bounded native-data loading for impulse development."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_data import (
    load_impulse_development_inputs,
)
from hypervector.research.cross_asset_impulse_models import CrossAssetImpulseConfig


def _config() -> CrossAssetImpulseConfig:
    return CrossAssetImpulseConfig(
        warmup_start=pd.Timestamp("2026-01-01T00:00:00Z"),
        development_start=pd.Timestamp("2026-01-01T00:10:00Z"),
        development_end=pd.Timestamp("2026-01-01T00:20:00Z"),
        impulse_return_minutes=2,
        lookback_minutes=6,
        minimum_valid_returns=5,
        cooldown_minutes=5,
        horizons_minutes=(2, 5),
    )


def _write_sources(root: Path) -> None:
    times = pd.date_range("2025-12-31T23:55:00Z", periods=35, freq="1min")
    for offset, symbol in enumerate(("BTC", "ETH", "SOL", "HYPE")):
        frame = pd.DataFrame(
            {
                "timestamp": times,
                "open": 100.0 + offset,
                "close": 100.1 + offset,
                "source": "hl",
            }
        )
        frame.loc[7, "source"] = "hl_gap_fill"
        path = root / "cache" / f"{symbol}_1m_365d.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)


def test_loader_selects_only_warmup_through_development_and_binds_identity(
    tmp_path: Path,
) -> None:
    _write_sources(tmp_path)

    frames, identity = load_impulse_development_inputs(tmp_path, _config())

    assert tuple(frames) == ("BTC", "ETH", "SOL", "HYPE")
    assert all(len(frame) == 20 for frame in frames.values())
    assert all(
        frame["timestamp"].iloc[0] == pd.Timestamp("2026-01-01T00:00:00Z")
        for frame in frames.values()
    )
    assert all(
        frame["timestamp"].iloc[-1] == pd.Timestamp("2026-01-01T00:19:00Z")
        for frame in frames.values()
    )
    assert identity["BTC"]["selected_rows"] == 20
    assert identity["BTC"]["native_rows"] == 19
    assert identity["BTC"]["gap_fill_rows"] == 1
    assert len(str(identity["BTC"]["selected_frame_sha256"])) == 64
    assert len(str(identity["BTC"]["bars"]["sha256"])) == 64


def test_loader_rejects_missing_minute_or_unknown_source(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    path = tmp_path / "cache" / "BTC_1m_365d.parquet"
    frame = pd.read_parquet(path)
    frame = frame.drop(index=10)
    frame.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="exact warmup and development window"):
        load_impulse_development_inputs(tmp_path, _config())

    _write_sources(tmp_path)
    frame = pd.read_parquet(path)
    frame.loc[10, "source"] = "binance"
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="unsupported source"):
        load_impulse_development_inputs(tmp_path, _config())


def test_loader_combines_explicit_source_bound_warmup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    _write_sources(tmp_path)
    for symbol in ("BTC", "ETH", "SOL", "HYPE"):
        path = tmp_path / "cache" / f"{symbol}_1m_365d.parquet"
        frame = pd.read_parquet(path)
        frame.loc[frame["timestamp"] >= config.development_start].to_parquet(
            path, index=False
        )

    def _warmup(
        data_root: Path,
        symbol: str,
        observed: CrossAssetImpulseConfig,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        assert data_root == tmp_path
        assert observed == config
        times = pd.date_range(
            config.warmup_start,
            config.development_start,
            freq="1min",
            inclusive="left",
        )
        return (
            pd.DataFrame(
                {
                    "timestamp": times,
                    "open": 99.0,
                    "close": 99.1,
                    "source": "hl",
                }
            ),
            {
                "source_files": [{"path": "warmup", "bytes": 1, "sha256": "warmup"}],
                "native_candle_rows": len(times),
                "trade_reconstruction_rows": 0,
                "gap_fill_rows": 0,
            },
        )

    monkeypatch.setattr(
        "hypervector.research.cross_asset_impulse_data._reconstructed_warmup",
        _warmup,
    )

    frames, identity = load_impulse_development_inputs(tmp_path, config)

    assert all(len(frame) == 20 for frame in frames.values())
    assert identity["BTC"]["warmup_source_files"][0]["path"] == "warmup"
    assert identity["BTC"]["trade_reconstruction_rows"] == 0
