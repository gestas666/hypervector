"""Exact 0x mark-gap overlay tests for HIP-3 lifecycle replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_price_archive import OxaPriceArchiveConfig
from hypervector.data.oxa_prices import (
    OxaPriceFetch,
    OxaPriceRequest,
    OxaPriceSnapshot,
    store_price_history,
)
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
    ArchiveRepairingHip3MarkSource,
)
from hypervector.research.hip3_shadow_lifecycle_inputs import (
    HIP3_EXACT_MARK_SOURCE,
    Hip3ShadowMark,
    mark_path_resolved,
)


class _BaseMarks:
    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        del data_root
        rows = (_mark_row(symbol, start_ms), _mark_row(symbol, end_ms))
        return rows, {"identity": "base"}

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        if evidence != {"identity": "base"}:
            raise ValueError("base evidence changed")


def test_archive_marks_repair_only_audit_declared_incomplete_windows(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    end = start + timedelta(minutes=15)
    audit = tmp_path / "audit.json"
    _write_audit(audit, start, end)
    archive = _archive(tmp_path, start, end)
    source = ArchiveRepairingHip3MarkSource(
        audit, archive, maximum_gap_ms=5_000, base=_BaseMarks()
    )

    rows, evidence = source.load(
        data_root=tmp_path,
        symbol="xyz:MU",
        start_ms=_ms(start),
        end_ms=_ms(end),
    )

    repaired = [row for row in rows if row["source"] == HIP3_ARCHIVE_REPAIR_MARK_SOURCE]
    marks = tuple(_typed_mark(row) for row in rows)
    assert repaired
    assert evidence["archive_repair_rows"] == len(repaired)
    assert mark_path_resolved(marks, _ms(start), _ms(end), 5_000)


def test_archive_mark_overlay_rehashes_every_consumed_input(tmp_path: Path) -> None:
    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    end = start + timedelta(minutes=15)
    audit = tmp_path / "audit.json"
    _write_audit(audit, start, end)
    source = ArchiveRepairingHip3MarkSource(
        audit, _archive(tmp_path, start, end), 5_000, base=_BaseMarks()
    )
    _rows, evidence = source.load(
        data_root=tmp_path,
        symbol="xyz:MU",
        start_ms=_ms(start),
        end_ms=_ms(end),
    )
    audit.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed"):
        source.require_unchanged(evidence)


def test_archive_overlay_leaves_its_own_incomplete_window_censored(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    middle = start + timedelta(minutes=15)
    end = middle + timedelta(minutes=15)
    audit = tmp_path / "audit.json"
    _write_audit_windows(audit, ((start, middle), (middle, end)))
    _store_prices(tmp_path, start, middle, range(_ms(start), _ms(middle), 4_000))
    sparse = (_ms(middle), _ms(middle) + 60_000, _ms(end) - 1_000)
    _store_prices(tmp_path, middle, end, sparse)
    archive = OxaPriceArchiveConfig(
        "xyz:MU",
        start,
        end,
        tmp_path,
        chunk=timedelta(minutes=15),
        maximum_gap=None,
        market_family="hip3",
    )
    source = ArchiveRepairingHip3MarkSource(
        audit, archive, maximum_gap_ms=5_000, base=_BaseMarks()
    )

    rows, evidence = source.load(
        data_root=tmp_path,
        symbol="xyz:MU",
        start_ms=_ms(start),
        end_ms=_ms(end),
    )

    repaired_times = {
        int(row["observed_ts_ms"])
        for row in rows
        if row["source"] == HIP3_ARCHIVE_REPAIR_MARK_SOURCE
    }
    assert evidence["archive_repaired_windows"] == 1
    assert evidence["archive_unresolved_windows"] == 1
    assert repaired_times
    assert all(timestamp <= _ms(middle) for timestamp in repaired_times)


def _archive(root: Path, start: datetime, end: datetime) -> OxaPriceArchiveConfig:
    _store_prices(root, start, end, range(_ms(start), _ms(end), 4_000))
    return OxaPriceArchiveConfig(
        "xyz:MU",
        start,
        end,
        root,
        chunk=timedelta(minutes=15),
        maximum_gap=None,
        market_family="hip3",
    )


def _write_audit(path: Path, start: datetime, end: datetime) -> None:
    _write_audit_windows(path, ((start, end),))


def _write_audit_windows(
    path: Path, windows: tuple[tuple[datetime, datetime], ...]
) -> None:
    rows = [
        {
            "bar_open_ms": _ms(start),
            "bar_close_ms": _ms(end),
            "mark": {"complete": False},
            "l2": {"complete": True},
            "resolved": False,
        }
        for start, end in windows
    ]
    payload = {
        "schema_version": "hip3_prospective_path_audit_v1",
        "mode": "prospective_public_venue_path_coverage",
        "source": {"symbol": "xyz:MU"},
        "coverage": {"timeframe_minutes": 15, "completed_bars": len(rows)},
        "bar_diagnostics": rows,
        "technical_assessment": {"unresolved_bars": len(rows)},
        "contract": {"report_only": True, "execution_authority": "none"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _store_prices(
    root: Path,
    start: datetime,
    end: datetime,
    timestamps: Iterable[int],
) -> None:
    request = OxaPriceRequest("xyz:MU", start, end, market_family="hip3")
    snapshots = tuple(
        OxaPriceSnapshot(
            datetime.fromtimestamp(int(timestamp) / 1_000, tz=UTC).isoformat(),
            int(timestamp),
            "100.0",
            "100.0",
            "100.0",
        )
        for timestamp in timestamps
    )
    store_price_history(root, request, OxaPriceFetch((), snapshots, True, None))


def _mark_row(symbol: str, timestamp_ms: int) -> dict[str, object]:
    return {
        "symbol": symbol,
        "observed_ts_ms": timestamp_ms,
        "received_ts_ns": timestamp_ms * 1_000_000,
        "mark_price": 100.0,
        "source": HIP3_EXACT_MARK_SOURCE,
    }


def _typed_mark(row: Mapping[str, object]) -> Hip3ShadowMark:
    timestamp = int(row["observed_ts_ms"])
    return Hip3ShadowMark(
        int(row["received_ts_ns"]),
        timestamp,
        float(row["mark_price"]),
        str(row["source"]),
    )


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)
