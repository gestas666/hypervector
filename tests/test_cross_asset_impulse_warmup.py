"""Tests for source-bound impulse warmup reconstruction."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_warmup import (
    reconstruct_impulse_warmup,
)


def _evidence(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _bundles(root: Path) -> tuple[Path, Path, pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T00:06:00Z")
    candle_bundle = root / "candles"
    trade_bundle = root / "trades"
    candle_bundle.mkdir()
    trade_bundle.mkdir()
    times = pd.date_range(start, end, freq="1min", inclusive="left")
    candles = pd.DataFrame(
        {
            "timestamp": times.delete(2),
            "open": [100.0, 101.0, 103.0, 104.0, 105.0],
            "high": [100.5, 101.5, 103.5, 104.5, 105.5],
            "low": [99.5, 100.5, 102.5, 103.5, 104.5],
            "close": [100.2, 101.2, 103.2, 104.2, 105.2],
            "volume": 1.0,
            "trade_count": 1,
            "source": "hl",
        }
    )
    candle_path = candle_bundle / "candles.parquet"
    candles.to_parquet(candle_path, index=False)
    _manifest(
        candle_bundle,
        {
            "source": "0xarchive_hyperliquid_candles",
            "symbol": "BTC",
            "interval": "1m",
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "row_count": len(candles),
            "complete": True,
            "files": {"candles.parquet": _evidence(candle_path)},
        },
    )
    trade_path = trade_bundle / "trades.jsonl.gz"
    rows = [
        _trade(times[2], 1, 102.0),
        _trade(times[2] + pd.Timedelta(seconds=30), 2, 102.2),
    ]
    with gzip.open(trade_path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    _manifest(
        trade_bundle,
        {
            "source": "0xarchive_hyperliquid_public_trades",
            "symbol": "BTC",
            "requested_start": times[2].isoformat(),
            "requested_end": times[4].isoformat(),
            "trade_count": len(rows),
            "normalization_version": "taker_only_v2",
            "surrogate_trade_id_count": 0,
            "unresolved_fill_groups": 0,
            "complete": True,
            "files": {"trades.jsonl.gz": _evidence(trade_path)},
        },
    )
    return candle_bundle, trade_bundle, start, end


def _trade(timestamp: pd.Timestamp, trade_id: int, price: float) -> dict[str, object]:
    return {
        "ts_exchange_ms": int(timestamp.timestamp() * 1000),
        "trade_id": trade_id,
        "aggressor_side": "buy",
        "price": price,
        "size": 1.0,
    }


def _manifest(bundle: Path, payload: dict[str, object]) -> None:
    (bundle / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_reconstructs_missing_native_minute_and_binds_all_evidence(
    tmp_path: Path,
) -> None:
    candles, trades, start, end = _bundles(tmp_path)

    frame, identity = reconstruct_impulse_warmup(
        candle_bundle=candles,
        trade_bundle=trades,
        symbol="BTC",
        start=start,
        end=end,
        repair_start=start + pd.Timedelta(minutes=2),
        repair_end=start + pd.Timedelta(minutes=4),
    )

    assert len(frame) == 6
    assert frame.loc[2, "open"] == 102.0
    assert frame.loc[2, "close"] == 102.2
    assert frame.loc[2, "source"] == "hl"
    assert identity["native_candle_rows"] == 5
    assert identity["trade_reconstruction_rows"] == 1
    assert identity["gap_fill_rows"] == 0
    assert len(identity["source_files"]) == 4


def test_verified_no_trade_minute_is_labeled_invalid(tmp_path: Path) -> None:
    candles, trades, start, end = _bundles(tmp_path)
    trade_path = trades / "trades.jsonl.gz"
    row = _trade(start + pd.Timedelta(minutes=3), 3, 103.1)
    with gzip.open(trade_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    manifest = json.loads((trades / "manifest.json").read_text(encoding="utf-8"))
    manifest["trade_count"] = 1
    manifest["files"]["trades.jsonl.gz"] = _evidence(trade_path)
    _manifest(trades, manifest)

    frame, identity = reconstruct_impulse_warmup(
        candle_bundle=candles,
        trade_bundle=trades,
        symbol="BTC",
        start=start,
        end=end,
        repair_start=start + pd.Timedelta(minutes=2),
        repair_end=start + pd.Timedelta(minutes=4),
    )

    assert frame.loc[2, "source"] == "hl_gap_fill"
    assert frame.loc[2, "close"] == frame.loc[1, "close"]
    assert identity["gap_fill_rows"] == 1


def test_rejects_tampered_bundle_or_wrong_identity(tmp_path: Path) -> None:
    candles, trades, start, end = _bundles(tmp_path)
    (candles / "candles.parquet").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="evidence (byte count|checksum) mismatch"):
        reconstruct_impulse_warmup(
            candle_bundle=candles,
            trade_bundle=trades,
            symbol="BTC",
            start=start,
            end=end,
            repair_start=start + pd.Timedelta(minutes=2),
            repair_end=start + pd.Timedelta(minutes=4),
        )


def test_rejects_trade_rows_outside_declared_repair_window(tmp_path: Path) -> None:
    candles, trades, start, end = _bundles(tmp_path)
    manifest = json.loads((trades / "manifest.json").read_text(encoding="utf-8"))
    manifest["requested_end"] = end.isoformat()
    _manifest(trades, manifest)

    with pytest.raises(ValueError, match="trade bundle identity"):
        reconstruct_impulse_warmup(
            candle_bundle=candles,
            trade_bundle=trades,
            symbol="BTC",
            start=start,
            end=end,
            repair_start=start + pd.Timedelta(minutes=2),
            repair_end=start + pd.Timedelta(minutes=4),
        )
