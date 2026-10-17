"""Book alignment marks missing book data instead of fabricating it.

Regressions:
- bars with no snapshot within tolerance (or with no book at all) received
  spread_bps=1.5, obi_5=0, depth 10/10, ratio 1.0 and so on, indistinguishable
  from real microstructure, and the gate then treated them as real;
- ``.zst`` snapshots were decompressed through ``shell=True`` with the path
  interpolated in single quotes and a hard-coded Homebrew binary;
- the SQLite connection leaked when the feature query failed.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

import hypervector.data.book_align as book_align
from hypervector.data.book_align import (
    BOOK_FEATURE_COLUMNS,
    align_orderbook_to_ohlcv,
    book_coverage_summary,
    gate_signals_by_orderbook,
    load_l2_sqlite_feature_samples,
)

_T0 = 1_784_827_380_000  # bar timestamps, one minute apart
_MIN = 60_000


def _bars(n: int = 4) -> pd.DataFrame:
    ts = [_T0 + i * _MIN for i in range(n)]
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(ts, unit="ms", utc=True),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
    )


def _book(rows: list[tuple[int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [ts for ts, _ in rows],
            "spread_bps": [3.0 for _ in rows],
            "obi_5": [obi for _, obi in rows],
            "obi_10": [obi for _, obi in rows],
            "bid_depth_10": [5.0 for _ in rows],
            "ask_depth_10": [4.0 for _ in rows],
            "book_depth_ratio": [1.25 for _ in rows],
            "micro_price_delta_bps": [0.1 for _ in rows],
        }
    )


def test_unmatched_bars_carry_nan_and_an_availability_flag() -> None:
    # Snapshots 10 s before bar 0 and bar 3; bars 1-2 are > 30 s from bar 0's snapshot.
    book = _book([(_T0 - 10_000, 0.5), (_T0 + 3 * _MIN - 10_000, 0.5)])

    aligned = align_orderbook_to_ohlcv(_bars(), book, max_tolerance_ms=30_000)

    assert aligned["book_available"].tolist() == [True, False, False, True]
    assert aligned["book_age_ms"].iloc[0] == 10_000
    assert aligned["book_age_ms"].iloc[3] == 10_000
    for column in BOOK_FEATURE_COLUMNS:
        assert aligned[column].iloc[1:3].isna().all(), column
    assert aligned["spread_bps"].iloc[0] == 3.0


def test_book_pressure_is_not_dragged_toward_fabricated_zeros() -> None:
    book = _book([(_T0 - 10_000, 0.5), (_T0 + 3 * _MIN - 10_000, 0.5)])

    aligned = align_orderbook_to_ohlcv(_bars(), book, max_tolerance_ms=30_000)

    # Every observed obi_5 is 0.5, so its EMA is 0.5 on every observed bar; the
    # old fillna(0.0) pulled bar 3 toward zero and filled bars 1-2 with values.
    assert aligned["book_pressure"].iloc[0] == pytest.approx(0.5)
    assert aligned["book_pressure"].iloc[3] == pytest.approx(0.5)
    assert aligned["book_pressure"].iloc[1:3].isna().all()


def test_fully_covered_alignment_is_numerically_unchanged() -> None:
    obis = [0.5, -0.2, 0.1, 0.3]
    book = _book([(_T0 + i * _MIN - 1_000, obi) for i, obi in enumerate(obis)])

    aligned = align_orderbook_to_ohlcv(_bars(), book)

    expected = pd.Series(obis).ewm(span=10, adjust=False).mean()
    np.testing.assert_allclose(aligned["book_pressure"].to_numpy(), expected.to_numpy())
    assert aligned["book_available"].all()


def test_empty_book_marks_every_bar_unavailable() -> None:
    aligned = align_orderbook_to_ohlcv(_bars(), pd.DataFrame())

    assert not aligned["book_available"].any()
    for column in BOOK_FEATURE_COLUMNS:
        assert aligned[column].isna().all(), column


def test_coverage_summary_reports_matched_bars_and_warns() -> None:
    book = _book([(_T0 - 10_000, 0.5)])
    aligned = align_orderbook_to_ohlcv(_bars(), book, max_tolerance_ms=30_000)

    summary = book_coverage_summary(aligned, max_tolerance_ms=30_000)

    assert summary["bars"] == 4
    assert summary["matched_bars"] == 1
    assert summary["book_coverage"] == pytest.approx(0.25)
    assert summary["max_tolerance_ms"] == 30_000
    assert summary["warnings"]

    none = book_coverage_summary(align_orderbook_to_ohlcv(_bars(), pd.DataFrame()))
    assert none["book_coverage"] == 0.0
    assert any("no bar" in w for w in none["warnings"])


def test_gate_passes_signals_through_where_the_book_is_missing() -> None:
    # Bar 0 has a real, blocking book (obi -0.9); bars 1-2 have no book.
    book = _book([(_T0 - 10_000, -0.9), (_T0 + 3 * _MIN - 10_000, 0.6)])
    aligned = align_orderbook_to_ohlcv(_bars(), book, max_tolerance_ms=30_000)
    entries = pd.Series([True, True, True, True])

    gated = gate_signals_by_orderbook(entries, aligned, direction="long", min_obi=0.1)

    # Previously the fabricated obi_5=0.0 blocked bars 1-2 under min_obi=0.1.
    assert gated.tolist() == [False, True, True, True]


# --- sqlite / zstd loading --------------------------------------------------


def _feature_db(path: Path, *, with_table: bool = True) -> None:
    with sqlite3.connect(path) as conn:
        if with_table:
            conn.execute(
                "CREATE TABLE feature_samples (coin TEXT, feature_time INTEGER, mid REAL,"
                " micro_price REAL, spread_bps REAL, obi_5 REAL, obi_10 REAL,"
                " bid_depth_10 REAL, ask_depth_10 REAL, aggressor_ratio_5s REAL,"
                " cancel_rate_5s REAL)"
            )
            conn.execute(
                "INSERT INTO feature_samples VALUES ('BTC', ?, 100, 100.01, 1, 0.1, 0.1, 5, 4, 0.5, 0.1)",
                (_T0,),
            )
        else:
            conn.execute("CREATE TABLE other (x INTEGER)")
    conn.close()


def test_sqlite_connection_is_closed_when_the_query_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "no_features.sqlite"
    _feature_db(db, with_table=False)
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(book_align.sqlite3, "connect", tracking_connect)

    with pytest.raises(Exception, match="feature_samples"):
        load_l2_sqlite_feature_samples(db)

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_zstd_is_invoked_without_a_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "x.sqlite.zst"
    src.write_bytes(b"not used")
    seen: dict[str, Any] = {}

    def fake_run(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(book_align.subprocess, "run", fake_run)
    monkeypatch.setattr(book_align.shutil, "which", lambda _name: "/usr/bin/true")

    with pytest.raises(RuntimeError, match="zstd decompression failed: boom"):
        load_l2_sqlite_feature_samples(src)

    assert isinstance(seen["args"], list)
    assert seen["args"][-2:] == ["--", str(src)]
    assert not seen["kwargs"].get("shell")
    assert not list(tmp_path.glob("*.sqlite")), "temp sqlite must be removed on failure"


@pytest.mark.skipif(
    shutil.which("zstd") is None and not Path("/opt/homebrew/bin/zstd").is_file(),
    reason="zstd executable not installed",
)
def test_zst_path_with_a_single_quote_loads(tmp_path: Path) -> None:
    db = tmp_path / "plain.sqlite"
    _feature_db(db)
    zstd = shutil.which("zstd") or "/opt/homebrew/bin/zstd"
    quoted = tmp_path / "o'brien.sqlite.zst"
    subprocess.run([zstd, "-q", "-o", str(quoted), "--", str(db)], check=True)

    frame = load_l2_sqlite_feature_samples(quoted)

    assert len(frame) == 1
    assert frame["ts_ms"].iloc[0] == _T0
