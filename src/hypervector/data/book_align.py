"""Orderbook L2 alignment and microstructure feature extraction.

Aligns historical L2 snapshots (JSONL or SQLite feature_samples) to OHLCV bar
timestamps with zero lookahead (point-in-time merge_asof).

Pipeline:
  OHLCV bar + L2 snapshot (at bar close) → book features / gate → metalabel → size
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import open_text_reader

# Fallback for launchd-style environments whose PATH lacks Homebrew.
_HOMEBREW_ZSTD = "/opt/homebrew/bin/zstd"
DEFAULT_MAX_TOLERANCE_MS = 300_000
# Book feature columns an aligned frame carries; NaN where no snapshot matched.
BOOK_FEATURE_COLUMNS = (
    "spread_bps",
    "obi_5",
    "obi_10",
    "bid_depth_10",
    "ask_depth_10",
    "book_depth_ratio",
    "micro_price_delta_bps",
    "book_pressure",
)


def load_l2_jsonl(path: Path | str) -> pd.DataFrame:
    """Load raw L2 orderbook snapshot JSONL into a clean DataFrame."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"L2 JSONL file not found: {p}")

    rows: list[dict[str, Any]] = []
    with open_text_reader(p) as f:
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
    try:
        if str(p).endswith(".zst"):
            # Decompress to a temp file without a shell: the path is one argv
            # element and "--" stops a leading "-" being read as an option.
            zstd = shutil.which("zstd") or _HOMEBREW_ZSTD
            if not Path(zstd).is_file():
                raise RuntimeError(
                    "zstd executable is required to read .zst orderbook snapshots"
                )
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                temp_sqlite = tmp.name
            with open(temp_sqlite, "wb") as out:
                res = subprocess.run(
                    [zstd, "-dc", "--", str(p)],
                    stdout=out,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            if res.returncode != 0:
                detail = (res.stderr or b"").decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"zstd decompression failed: {detail}")
            target_path = temp_sqlite

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
        with closing(sqlite3.connect(target_path)) as conn:
            df = pd.read_sql_query(query, conn, params=(coin,))

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
    max_tolerance_ms: int = DEFAULT_MAX_TOLERANCE_MS,
) -> pd.DataFrame:
    """Point-in-time merge_asof of orderbook microstructure features onto OHLCV bars.

    Uses exact bar timestamp (or timestamp derived from DatetimeIndex).
    Guarantees no future peek: each bar receives the latest orderbook snapshot
    recorded BEFORE or AT that bar's timestamp, within ``max_tolerance_ms``.

    Missing book data is never invented: a bar with no snapshot in tolerance
    (or every bar, when ``df_book`` is empty) keeps NaN book features. Two
    columns say what was matched: ``book_available`` (bool) and
    ``book_age_ms`` (bar ts minus matched snapshot ts; NaN when unmatched).
    ``book_pressure`` is the EMA of the observed ``obi_5`` values only.
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
        for column in BOOK_FEATURE_COLUMNS:
            bars[column] = np.nan
        bars["book_available"] = False
        bars["book_age_ms"] = np.nan
        return bars

    bars["__bar_order"] = np.arange(len(bars), dtype=np.int64)
    bars_sorted = bars.sort_values("ts_ms").reset_index(drop=True)
    book_sorted = df_book.sort_values("ts_ms").reset_index(drop=True)
    book_sorted["__book_ts_ms"] = book_sorted["ts_ms"].astype(np.float64)

    # Point-in-time backward merge_asof
    merged = pd.merge_asof(
        bars_sorted,
        book_sorted,
        on="ts_ms",
        direction="backward",
        tolerance=max_tolerance_ms,
        suffixes=("", "_book"),
    )
    matched_ts = merged.pop("__book_ts_ms")
    available = matched_ts.notna()
    merged["book_available"] = available.to_numpy(dtype=bool)
    merged["book_age_ms"] = merged["ts_ms"].astype(np.float64) - matched_ts

    # Rolling book pressure: EMA over observed obi_5 only, NaN on unmatched bars.
    if "obi_5" in merged.columns:
        pressure = merged["obi_5"].astype(float).ewm(span=10, adjust=False).mean()
        merged["book_pressure"] = pressure.where(available)

    merged = merged.sort_values("__bar_order")
    order = merged.pop("__bar_order").to_numpy(dtype=np.int64)
    merged.index = original_index.take(order)
    return merged


def book_coverage_summary(
    df_aligned: pd.DataFrame,
    *,
    max_tolerance_ms: int = DEFAULT_MAX_TOLERANCE_MS,
) -> dict[str, Any]:
    """How many aligned bars carry a real snapshot, for reports and CLI JSON."""
    bars = int(len(df_aligned))
    if "book_available" in df_aligned.columns:
        available = df_aligned["book_available"].fillna(False).astype(bool)
    else:
        available = pd.Series(False, index=df_aligned.index)
    matched = int(available.sum())
    coverage = matched / bars if bars else 0.0
    first = last = None
    if matched and {"ts_ms", "book_age_ms"}.issubset(df_aligned.columns):
        snap_ms = (
            df_aligned.loc[available, "ts_ms"].astype(np.float64)
            - df_aligned.loc[available, "book_age_ms"].astype(np.float64)
        )
        first = pd.Timestamp(int(snap_ms.min()), unit="ms", tz="UTC").isoformat()
        last = pd.Timestamp(int(snap_ms.max()), unit="ms", tz="UTC").isoformat()
    warnings: list[str] = []
    if bars and not matched:
        warnings.append(
            f"no bar has an order-book snapshot within {max_tolerance_ms} ms; "
            "every book column is missing (NaN)"
        )
    elif matched < bars:
        warnings.append(
            f"{bars - matched} of {bars} bars ({1.0 - coverage:.1%}) have no "
            f"order-book snapshot within {max_tolerance_ms} ms; their book columns are NaN"
        )
    return {
        "bars": bars,
        "matched_bars": matched,
        "book_coverage": coverage,
        "book_first_ts_utc": first,
        "book_last_ts_utc": last,
        "max_tolerance_ms": int(max_tolerance_ms),
        "warnings": warnings,
    }


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

    If book data is unavailable or unpopulated (NaN), the signal passes through:
    only an observed book can block an entry.
    """
    if not entries.any() or df_aligned.empty:
        return entries

    gate_ok = pd.Series(True, index=entries.index)
    df = df_aligned.reset_index(drop=True)

    def observed(column: str) -> np.ndarray:
        return df[column].to_numpy(dtype=float)

    if "spread_bps" in df.columns:
        spread = observed("spread_bps")
        gate_ok = gate_ok & (np.isnan(spread) | (spread <= max_spread_bps))

    if direction == "long":
        if "obi_5" in df.columns:
            obi = observed("obi_5")
            gate_ok = gate_ok & (np.isnan(obi) | (obi >= min_obi))
        if "book_depth_ratio" in df.columns:
            ratio = observed("book_depth_ratio")
            gate_ok = gate_ok & (np.isnan(ratio) | (ratio >= min_depth_ratio))
    else:  # short
        if "obi_5" in df.columns:
            obi = observed("obi_5")
            gate_ok = gate_ok & (np.isnan(obi) | (obi <= -min_obi))
        if "book_depth_ratio" in df.columns:
            max_dr = 1.0 / max(min_depth_ratio, 1e-4)
            ratio = observed("book_depth_ratio")
            gate_ok = gate_ok & (np.isnan(ratio) | (ratio <= max_dr))

    return entries & gate_ok.fillna(True).astype(bool)


