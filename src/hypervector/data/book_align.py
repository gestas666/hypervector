"""Orderbook L2 alignment and microstructure feature extraction.

Aligns historical L2 snapshots (JSONL or SQLite feature_samples) to OHLCV bar
timestamps with zero lookahead (point-in-time merge_asof).

Pipeline:
  OHLCV bar + L2 snapshot (at bar close) → book features / gate → metalabel → size
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_l2_jsonl(path: Path | str) -> pd.DataFrame:
    """Load raw L2 orderbook snapshot JSONL into a clean DataFrame."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"L2 JSONL file not found: {p}")

    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            ts_ms = float(row.get("ts_exchange_ms") or row.get("ts_recv_ms") or 0.0)
            best_bid = float(row.get("best_bid") or 0.0)
            best_ask = float(row.get("best_ask") or 0.0)

            bids = row.get("bids") or []
            asks = row.get("asks") or []

            bid_vol_5 = sum(float(b.get("sz", 0.0)) for b in bids[:5])
            ask_vol_5 = sum(float(a.get("sz", 0.0)) for a in asks[:5])
            bid_vol_10 = sum(float(b.get("sz", 0.0)) for b in bids[:10])
            ask_vol_10 = sum(float(a.get("sz", 0.0)) for a in asks[:10])

            denom_5 = bid_vol_5 + ask_vol_5
            obi_5 = (bid_vol_5 - ask_vol_5) / denom_5 if denom_5 > 0 else 0.0

            denom_10 = bid_vol_10 + ask_vol_10
            obi_10 = (bid_vol_10 - ask_vol_10) / denom_10 if denom_10 > 0 else 0.0

            mid = (
                (best_bid + best_ask) / 2.0 if (best_bid > 0 and best_ask > 0) else 0.0
            )
            spread_bps = ((best_ask - best_bid) / mid * 10_000.0) if mid > 0 else 0.0

            # Microprice = (ask_vol_1 * best_bid + bid_vol_1 * best_ask) / (bid_vol_1 + ask_vol_1)
            b1_sz = float(bids[0]["sz"]) if bids else 0.0
            a1_sz = float(asks[0]["sz"]) if asks else 0.0
            micro_denom = b1_sz + a1_sz
            if micro_denom > 0 and best_bid > 0 and best_ask > 0:
                micro_price = (a1_sz * best_bid + b1_sz * best_ask) / micro_denom
                micro_price_delta_bps = (micro_price - mid) / mid * 10_000.0
            else:
                micro_price = mid
                micro_price_delta_bps = 0.0

            depth_ratio = (bid_vol_10 / ask_vol_10) if ask_vol_10 > 0 else 1.0

            rows.append(
                {
                    "ts_ms": ts_ms,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "mid": mid,
                    "spread_bps": spread_bps,
                    "obi_5": obi_5,
                    "obi_10": obi_10,
                    "bid_depth_10": bid_vol_10,
                    "ask_depth_10": ask_vol_10,
                    "book_depth_ratio": depth_ratio,
                    "micro_price": micro_price,
                    "micro_price_delta_bps": micro_price_delta_bps,
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["ts_ms"] = df["ts_ms"].astype(np.int64)
        df = df.sort_values("ts_ms").reset_index(drop=True)
    return df


def load_l2_sqlite_feature_samples(
    zst_or_sqlite_path: Path | str, coin: str = "BTC"
) -> pd.DataFrame:
    """Load orderbook features from impulse_calibration_snapshot.sqlite (.zst or raw)."""
    p = Path(zst_or_sqlite_path)
    if not p.is_file():
        raise FileNotFoundError(f"Orderbook snapshot file not found: {p}")

    temp_sqlite: str | None = None
    target_path = str(p)

    if str(p).endswith(".zst"):
        # Extract sqlite to temp location using zstd
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            temp_sqlite = tmp.name
        cmd = f"/opt/homebrew/bin/zstd -dc '{p}' > '{temp_sqlite}'"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            if os.path.exists(temp_sqlite):
                os.remove(temp_sqlite)
            raise RuntimeError(f"zstd decompression failed: {res.stderr}")
        target_path = temp_sqlite

    try:
        conn = sqlite3.connect(target_path)
        query = """
            SELECT
                feature_time as ts_ms,
                mid,
                micro_price,
                spread_bps,
                obi_5,
                obi_10,
                bid_depth_10,
                ask_depth_10,
                aggressor_ratio_5s,
                cancel_rate_5s
            FROM feature_samples
            WHERE coin = ?
            ORDER BY feature_time ASC
        """
        df = pd.read_sql_query(query, conn, params=(coin,))
        conn.close()

        if not df.empty:
            df["ts_ms"] = df["ts_ms"].astype(np.int64)
            df["book_depth_ratio"] = np.where(
                df["ask_depth_10"] > 0,
                df["bid_depth_10"] / df["ask_depth_10"],
                1.0,
            )
            df["micro_price_delta_bps"] = np.where(
                df["mid"] > 0,
                (df["micro_price"] - df["mid"]) / df["mid"] * 10_000.0,
                0.0,
            )
        return df
    finally:
        if temp_sqlite and os.path.exists(temp_sqlite):
            try:
                os.remove(temp_sqlite)
            except OSError:
                pass


def _to_ts_ms_series(ts_col: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    if hasattr(ts_col, "dt"):
        ts_naive = ts_col.dt.tz_localize(None) if ts_col.dt.tz is not None else ts_col
        return (ts_naive.astype("datetime64[ns]").astype(np.int64) // 10**6).to_numpy()
    else:
        ts_naive = ts_col.tz_localize(None) if ts_col.tz is not None else ts_col
        return (ts_naive.astype("datetime64[ns]").astype(np.int64) // 10**6).to_numpy()


def align_orderbook_to_ohlcv(
    df_ohlcv: pd.DataFrame,
    df_book: pd.DataFrame,
    max_tolerance_ms: int = 300_000,
) -> pd.DataFrame:
    """Point-in-time merge_asof of orderbook microstructure features onto OHLCV bars.

    Uses exact bar timestamp (or timestamp derived from DatetimeIndex).
    Guarantees no future peek: each bar receives the latest orderbook snapshot
    recorded BEFORE or AT that bar's timestamp.
    """
    if df_ohlcv.empty:
        return df_ohlcv

    bars = df_ohlcv.copy()
    original_index = bars.index.copy()
    if "ts_ms" not in bars.columns:
        if "timestamp" in bars.columns:
            ts_col = pd.to_datetime(bars["timestamp"], utc=True, errors="coerce")
            bars["ts_ms"] = _to_ts_ms_series(ts_col)
        elif isinstance(bars.index, pd.DatetimeIndex):
            ts_col = pd.DatetimeIndex(bars.index)
            if ts_col.tz is None:
                ts_col = ts_col.tz_localize("UTC")
            bars["ts_ms"] = _to_ts_ms_series(ts_col)
        else:
            raise ValueError(
                "OHLCV DataFrame must have 'timestamp', 'ts_ms', or DatetimeIndex"
            )

    if df_book.empty:
        # Fill defaults when no book data exists
        defaults = {
            "spread_bps": 1.5,
            "obi_5": 0.0,
            "obi_10": 0.0,
            "bid_depth_10": 10.0,
            "ask_depth_10": 10.0,
            "book_depth_ratio": 1.0,
            "micro_price_delta_bps": 0.0,
            "book_pressure": 0.0,
        }
        for k, v in defaults.items():
            bars[k] = v
        return bars

    bars["__bar_order"] = np.arange(len(bars), dtype=np.int64)
    bars_sorted = bars.sort_values("ts_ms").reset_index(drop=True)
    book_sorted = df_book.sort_values("ts_ms").reset_index(drop=True)

    # Point-in-time backward merge_asof
    merged = pd.merge_asof(
        bars_sorted,
        book_sorted,
        on="ts_ms",
        direction="backward",
        tolerance=max_tolerance_ms,
        suffixes=("", "_book"),
    )

    # Compute rolling book pressure (EMA of obi_5)
    if "obi_5" in merged.columns:
        merged["book_pressure"] = (
            merged["obi_5"].fillna(0.0).ewm(span=10, adjust=False).mean()
        )

    # Fill NaNs with neutral defaults
    fill_dict = {
        "spread_bps": 1.5,
        "obi_5": 0.0,
        "obi_10": 0.0,
        "bid_depth_10": 10.0,
        "ask_depth_10": 10.0,
        "book_depth_ratio": 1.0,
        "micro_price_delta_bps": 0.0,
        "book_pressure": 0.0,
    }
    for col, val in fill_dict.items():
        if col in merged.columns:
            merged[col] = merged[col].fillna(val)

    merged = merged.sort_values("__bar_order")
    order = merged.pop("__bar_order").to_numpy(dtype=np.int64)
    merged.index = original_index.take(order)
    return merged


def gate_signals_by_orderbook(
    entries: pd.Series,
    df_aligned: pd.DataFrame,
    *,
    direction: str = "long",
    max_spread_bps: float = 10.0,
    min_obi: float = -0.5,
    min_depth_ratio: float = 0.2,
) -> pd.Series:
    """Filter signal entries using orderbook spread, imbalance, and depth gates.

    If book data is unavailable or unpopulated, defaults to passing signals through.
    """
    if not entries.any() or df_aligned.empty:
        return entries

    gate_ok = pd.Series(True, index=entries.index)
    df = df_aligned.reset_index(drop=True)

    if "spread_bps" in df.columns:
        gate_ok = gate_ok & (df["spread_bps"].to_numpy() <= max_spread_bps)

    if direction == "long":
        if "obi_5" in df.columns:
            gate_ok = gate_ok & (df["obi_5"].to_numpy() >= min_obi)
        if "book_depth_ratio" in df.columns:
            gate_ok = gate_ok & (df["book_depth_ratio"].to_numpy() >= min_depth_ratio)
    else:  # short
        if "obi_5" in df.columns:
            gate_ok = gate_ok & (df["obi_5"].to_numpy() <= -min_obi)
        if "book_depth_ratio" in df.columns:
            max_dr = 1.0 / max(min_depth_ratio, 1e-4)
            gate_ok = gate_ok & (df["book_depth_ratio"].to_numpy() <= max_dr)

    return entries & gate_ok.fillna(True).astype(bool)
