"""Contracts for manifest-bound Cipher OHLCV candle inputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cipher_suite_candles import (
    load_cipher_ohlcv_from_candle_bundle,
)


def _bundle(path: Path, symbol: str = "HYPE") -> Path:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=index) for index in range(1_270)]
    times.pop(5)
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": [100.0] * len(times),
            "high": [101.0] * len(times),
            "low": [99.0] * len(times),
            "close": [100.5] * len(times),
            "volume": [1.0] * len(times),
            "source": ["hl"] * len(times),
        }
    )
    path.mkdir()
    candles = path / "candles.parquet"
    frame.to_parquet(candles, index=False)
    manifest = {
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_candles",
        "symbol": symbol,
        "interval": "1m",
        "requested_start": start.isoformat(),
        "requested_end": (start + timedelta(minutes=1_270)).isoformat(),
        "row_count": len(frame),
        "complete": True,
        "files": {"candles.parquet": file_evidence(candles)},
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_candle_bundle_loads_bounded_five_minute_inputs(tmp_path: Path) -> None:
    """Verified native candles retain warmup/lookahead and labeled gap repair."""
    bundle = _bundle(tmp_path / "bundle")

    inputs, evidence = load_cipher_ohlcv_from_candle_bundle(
        bundle,
        "HYPE",
        datetime(2026, 1, 1, 20, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 20, 50, tzinfo=UTC),
        history_bars=240,
        horizon_bars=4,
    )

    assert len(inputs.bars) == 254
    assert inputs.bars.iloc[0]["bar_open_at"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert evidence["gap_fill_rows"] == 1
    assert evidence["symbol"] == "HYPE"


def test_candle_bundle_rejects_symbol_misbinding(tmp_path: Path) -> None:
    """A HYPE file cannot be silently relabeled as ETH research evidence."""
    bundle = _bundle(tmp_path / "bundle")

    with pytest.raises(ValueError, match="identity"):
        load_cipher_ohlcv_from_candle_bundle(
            bundle,
            "ETH",
            datetime(2026, 1, 1, 20, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 20, 50, tzinfo=UTC),
            history_bars=240,
            horizon_bars=4,
        )


def test_candle_bundle_rejects_changed_parquet(tmp_path: Path) -> None:
    """Changed source bytes invalidate the manifest before signal research."""
    bundle = _bundle(tmp_path / "bundle")
    (bundle / "candles.parquet").write_bytes(b"changed")

    with pytest.raises(ValueError, match="byte count mismatch"):
        load_cipher_ohlcv_from_candle_bundle(
            bundle,
            "HYPE",
            datetime(2026, 1, 1, 20, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 20, 50, tzinfo=UTC),
            history_bars=240,
            horizon_bars=4,
        )
