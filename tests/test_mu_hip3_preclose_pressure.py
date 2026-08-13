"""Causal MU pre-close HIP-3 pressure evidence contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
from hypervector.data.oxa_history import (
    OxaBookFetch,
    OxaBookPage,
    OxaBookRequest,
    OxaBookSnapshot,
    OxaLevel,
    store_orderbook_history,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.live.mu_hip3_preclose_pressure import (
    MU_PRESSURE_SOURCE,
    MuAssetLedgerBinding,
    MuHip3LedgerPreclosePressureSource,
)
from hypervector.research.hip3_midpoint_bars import build_hip3_midpoint_bars

_OPEN_MS = 1_785_999_600_000
_CLOSE_MS = _OPEN_MS + 900_000


def _book(
    exchange_ms: int,
    recv_ms: int,
    *,
    bid_size: float = 3.0,
    ask_size: float = 1.0,
) -> dict[str, object]:
    return {
        "source": MU_PRESSURE_SOURCE,
        "symbol": "xyz:MU",
        "exchange_ts_ms": exchange_ms,
        "recv_ts_ms": recv_ms,
        "bids": [
            {"price": 99.9 - position * 0.1, "size": bid_size, "orders": 1}
            for position in range(10)
        ],
        "asks": [
            {"price": 100.1 + position * 0.1, "size": ask_size, "orders": 1}
            for position in range(10)
        ],
    }


def _asset_row(book: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": "mu_breakout_shadow_xyz:mu",
        "payload": book,
    }


def _cohort_row(book: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "market_books",
        "payload": {"books": {"xyz:MU": book}},
    }


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source(
    tmp_path: Path,
    asset_rows: list[dict[str, object]],
    cohort_rows: list[dict[str, object]] | None = None,
    *,
    tail_bytes: int = 512 * 1_024,
) -> MuHip3LedgerPreclosePressureSource:
    asset = tmp_path / "xyz:mu.jsonl"
    cohort = tmp_path / "cohort.jsonl"
    _write(asset, asset_rows)
    _write(cohort, cohort_rows or [])
    return MuHip3LedgerPreclosePressureSource(
        asset_binding=MuAssetLedgerBinding(
            symbol="xyz:MU",
            path=asset,
            profile_id="mu_breakout_shadow_xyz:mu",
        ),
        cohort_ledger=cohort,
        tail_bytes=tail_bytes,
    )


def test_completed_bar_uses_exact_exchange_window_and_receipt_cutoff(
    tmp_path: Path,
) -> None:
    rows = [
        _asset_row(_book(_OPEN_MS - 1, _OPEN_MS - 1)),
        _asset_row(_book(_OPEN_MS, _OPEN_MS + 10, bid_size=1.0, ask_size=1.0)),
        _asset_row(_book(_CLOSE_MS, _CLOSE_MS + 1)),
        _asset_row(_book(_CLOSE_MS - 5_000, _CLOSE_MS + 100)),
        _asset_row(_book(_CLOSE_MS - 1_000, _CLOSE_MS + 20_000)),
    ]
    source = _source(tmp_path, rows)

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS + 1_000,
    )

    assert evidence.source == MU_PRESSURE_SOURCE
    assert evidence.snapshot_count == 2
    assert evidence.last_exchange_ts_ms == _CLOSE_MS - 5_000
    assert evidence.last_recv_ts_ms == _CLOSE_MS + 100
    assert evidence.end_boundary_age_ms == 5_000
    assert evidence.imbalance_10 == pytest.approx(0.5)
    assert evidence.fresh is True
    assert evidence.scan_complete is True


def test_identical_asset_cohort_copies_dedupe_but_conflicts_fail(
    tmp_path: Path,
) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    first = _book(_OPEN_MS + 1_000, _OPEN_MS + 1_100)
    last = _book(_CLOSE_MS - 1_000, _CLOSE_MS - 900)
    source = _source(
        tmp_path,
        [_asset_row(proof), _asset_row(first), _asset_row(last)],
        [_cohort_row(proof), _cohort_row(first), _cohort_row(last)],
    )

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.snapshot_count == 2

    conflict = _book(
        _CLOSE_MS - 1_000,
        _CLOSE_MS - 800,
        bid_size=1.0,
        ask_size=3.0,
    )
    _write(tmp_path / "cohort.jsonl", [_cohort_row(proof), _cohort_row(conflict)])
    with pytest.raises(ValueError, match="conflicting exchange timestamp"):
        source.completed_bar(
            "xyz:MU",
            bar_open_ms=_OPEN_MS,
            bar_close_ms=_CLOSE_MS,
            observed_at_ms=_CLOSE_MS,
        )


def test_truncated_reverse_tail_is_unresolved_even_with_fresh_rows(
    tmp_path: Path,
) -> None:
    rows = [_asset_row(_book(_OPEN_MS - 1, _OPEN_MS - 1))]
    rows.extend(
        _asset_row(_book(_OPEN_MS + position * 1_000, _OPEN_MS + position * 1_000))
        for position in range(1, 40)
    )
    source = _source(tmp_path, rows, tail_bytes=2_000)

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.scan_complete is False
    assert evidence.fresh is False
    assert evidence.status == "truncated_ledger_tail"


def test_future_received_old_exchange_cannot_prove_truncated_scan(
    tmp_path: Path,
) -> None:
    rows = [
        _asset_row(_book(_OPEN_MS + position * 1_000, _OPEN_MS + position * 1_000))
        for position in range(1, 40)
    ]
    rows.append(_asset_row(_book(_OPEN_MS - 1, _CLOSE_MS + 100_000)))
    source = _source(tmp_path, rows, tail_bytes=6_000)

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.scan_complete is False
    assert evidence.fresh is False
    assert evidence.status == "truncated_ledger_tail"


def test_future_received_row_cannot_change_asof_identity_validation(
    tmp_path: Path,
) -> None:
    proof = _asset_row(_book(_OPEN_MS - 1, _OPEN_MS - 1))
    first = _asset_row(_book(_OPEN_MS + 1_000, _OPEN_MS + 1_100))
    last = _asset_row(_book(_CLOSE_MS - 1_000, _CLOSE_MS - 900))
    future = _asset_row(_book(_CLOSE_MS - 500, _CLOSE_MS + 20_000))
    future["profile_id"] = "portfolio_v25_xyz:sp500"
    source = _source(tmp_path, [proof, first, last, future])

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.fresh is True
    assert evidence.last_exchange_ts_ms == _CLOSE_MS - 1_000


def test_rejects_non_top_ten_or_wrong_source_book(tmp_path: Path) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    malformed = _book(_OPEN_MS + 1, _OPEN_MS + 2)
    malformed["bids"] = malformed["bids"][:9]
    source = _source(tmp_path, [_asset_row(proof), _asset_row(malformed)])

    with pytest.raises(ValueError, match="at least ten"):
        source.completed_bar(
            "xyz:MU",
            bar_open_ms=_OPEN_MS,
            bar_close_ms=_CLOSE_MS,
            observed_at_ms=_CLOSE_MS,
        )


def test_rejects_receipt_timestamp_before_exchange_timestamp(tmp_path: Path) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    impossible = _book(_OPEN_MS + 1_000, _OPEN_MS + 999)
    source = _source(tmp_path, [_asset_row(proof), _asset_row(impossible)])

    with pytest.raises(ValueError, match="receipt timestamp precedes exchange"):
        source.completed_bar(
            "xyz:MU",
            bar_open_ms=_OPEN_MS,
            bar_close_ms=_CLOSE_MS,
            observed_at_ms=_CLOSE_MS,
        )


@pytest.mark.parametrize("failure", ["unordered", "crossed"])
def test_rejects_unordered_or_crossed_top_ten_book(
    tmp_path: Path,
    failure: str,
) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    malformed = _book(_OPEN_MS + 1_000, _OPEN_MS + 1_100)
    if failure == "unordered":
        malformed["bids"][1]["price"] = malformed["bids"][0]["price"] + 1.0
    else:
        malformed["asks"][0]["price"] = malformed["bids"][0]["price"]
    source = _source(tmp_path, [_asset_row(proof), _asset_row(malformed)])

    with pytest.raises(ValueError, match="ordered and non-crossed"):
        source.completed_bar(
            "xyz:MU",
            bar_open_ms=_OPEN_MS,
            bar_close_ms=_CLOSE_MS,
            observed_at_ms=_CLOSE_MS,
        )


def test_asset_ledger_binding_accepts_production_payload_without_symbol(
    tmp_path: Path,
) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    first = _book(_OPEN_MS + 1_000, _OPEN_MS + 1_100)
    last = _book(_CLOSE_MS - 1_000, _CLOSE_MS - 900)
    for book in (proof, first, last):
        book.pop("symbol")
    source = _source(
        tmp_path,
        [_asset_row(proof), _asset_row(first), _asset_row(last)],
    )

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.fresh is True
    assert evidence.snapshot_count == 2


def test_no_symbol_asset_row_rejects_conflicting_profile_binding(
    tmp_path: Path,
) -> None:
    books = [
        _book(_OPEN_MS - 1, _OPEN_MS - 1),
        _book(_OPEN_MS + 1_000, _OPEN_MS + 1_100),
        _book(_CLOSE_MS - 1_000, _CLOSE_MS - 900),
    ]
    rows = [_asset_row(book) for book in books]
    for book in books:
        book.pop("symbol")
    for row in rows:
        row["profile_id"] = "portfolio_v25_xyz:sp500"
    asset = tmp_path / "xyz:mu.jsonl"
    cohort = tmp_path / "cohort.jsonl"
    _write(asset, rows)
    _write(cohort, [])
    source = MuHip3LedgerPreclosePressureSource(
        asset_binding=MuAssetLedgerBinding(
            symbol="xyz:MU",
            path=asset,
            profile_id="mu_breakout_shadow_xyz:mu",
        ),
        cohort_ledger=cohort,
    )

    with pytest.raises(ValueError, match="profile identity"):
        source.completed_bar(
            "xyz:MU",
            bar_open_ms=_OPEN_MS,
            bar_close_ms=_CLOSE_MS,
            observed_at_ms=_CLOSE_MS,
        )


def test_short_file_starting_midbar_is_not_complete(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        [
            _asset_row(_book(_OPEN_MS + 600_000, _OPEN_MS + 600_100)),
            _asset_row(_book(_CLOSE_MS - 1_000, _CLOSE_MS - 900)),
        ],
    )

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.scan_complete is False
    assert evidence.fresh is False


def test_delayed_old_exchange_cannot_prove_truncated_scan(
    tmp_path: Path,
) -> None:
    rows = [
        _asset_row(_book(_OPEN_MS + position * 1_000, _OPEN_MS + position * 1_000))
        for position in range(1, 40)
    ]
    rows.append(_asset_row(_book(_OPEN_MS - 1, _CLOSE_MS - 500)))
    source = _source(tmp_path, rows, tail_bytes=6_000)

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.scan_complete is False
    assert evidence.fresh is False


def _archive_snapshot(book: dict[str, object]) -> OxaBookSnapshot:
    timestamp_ms = int(book["exchange_ts_ms"])
    timestamp = datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
    bids = tuple(
        OxaLevel(str(level["price"]), str(level["size"]), 1) for level in book["bids"]
    )
    asks = tuple(
        OxaLevel(str(level["price"]), str(level["size"]), 1) for level in book["asks"]
    )
    return OxaBookSnapshot(
        symbol="xyz:MU",
        timestamp=timestamp.isoformat(),
        ts_exchange_ms=timestamp_ms,
        bids=bids,
        asks=asks,
    )


def _archive_database(
    root: Path,
    path: Path,
    books: tuple[dict[str, object], ...],
) -> pd.Timestamp:
    start = datetime.fromtimestamp(_OPEN_MS / 1_000, tz=UTC)
    end = datetime.fromtimestamp(_CLOSE_MS / 1_000, tz=UTC)
    request = OxaBookRequest(
        "xyz:MU",
        start,
        end,
        depth=10,
        market_family="hip3",
    )
    snapshots = tuple(_archive_snapshot(book) for book in books)
    page = OxaBookPage("mu-parity", None, snapshots, 0, {"success": True})
    store_orderbook_history(
        root,
        request,
        OxaBookFetch((page,), snapshots, True, None, 0),
    )
    ResearchDatabase(path).ingest_archive(
        OxaArchiveAuditConfig(
            symbol="xyz:MU",
            start=start,
            end=end,
            data_root=root,
            depth=10,
            market_family="hip3",
            book_only=True,
        )
    )
    return pd.Timestamp(start)


def test_ledger_pressure_matches_production_archive_decision_row(
    tmp_path: Path,
) -> None:
    database = tmp_path / "archive.duckdb"
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    first = _book(
        _OPEN_MS + 1_000,
        _OPEN_MS + 1_100,
        bid_size=1.0,
        ask_size=1.0,
    )
    last = _book(_CLOSE_MS - 1_000, _CLOSE_MS - 900)
    start = _archive_database(tmp_path / "archive", database, (first, last))
    archive = build_hip3_midpoint_bars(database, symbol="xyz:MU").bars.loc[start]
    source = _source(
        tmp_path,
        [_asset_row(proof), _asset_row(first), _asset_row(last)],
    )

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.imbalance_10 == archive["decision_imbalance_10"]
    assert evidence.snapshot_count == archive["source_snapshot_count"]
    assert evidence.end_boundary_age_ms == archive["end_boundary_age_ms"]
    assert evidence.fresh == (
        archive["source_snapshot_count"] >= 2
        and archive["end_boundary_age_ms"] <= 15_000
    )


def test_postclose_and_future_received_rows_do_not_change_archive_parity(
    tmp_path: Path,
) -> None:
    proof = _book(_OPEN_MS - 1, _OPEN_MS - 1)
    first = _book(_OPEN_MS + 1_000, _OPEN_MS + 1_100)
    last = _book(_CLOSE_MS - 1_000, _CLOSE_MS - 900)
    source = _source(
        tmp_path,
        [
            _asset_row(proof),
            _asset_row(first),
            _asset_row(last),
            _asset_row(_book(_CLOSE_MS - 500, _CLOSE_MS + 1)),
            _asset_row(_book(_CLOSE_MS, _CLOSE_MS)),
        ],
    )

    evidence = source.completed_bar(
        "xyz:MU",
        bar_open_ms=_OPEN_MS,
        bar_close_ms=_CLOSE_MS,
        observed_at_ms=_CLOSE_MS,
    )

    assert evidence.snapshot_count == 2
    assert evidence.last_exchange_ts_ms == _CLOSE_MS - 1_000
