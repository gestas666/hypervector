"""Incremental, compact execution history for live cohort telemetry."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.multi_asset_cohort_history import compatible_execution_rows
from hypervector.live.multi_asset_cohort_history import execution_row_is_compatible
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_ledger import AssetLiveLedgerCursor


class CohortAssetHistoryCache:
    """Read each asset ledger once, then consume only its validated suffix."""

    def __init__(self, ledgers: Mapping[str, AssetLiveLedger]) -> None:
        self._ledgers = dict(ledgers)
        self._histories: dict[str, list[dict[str, object]]] = {}
        self._cursors: dict[str, AssetLiveLedgerCursor] = {}
        for symbol, ledger in self._ledgers.items():
            rows = compatible_execution_rows(ledger)
            self._histories[symbol] = _compact_rows(rows, ledger.run_id)
            self._cursors[symbol] = ledger.end_cursor()

    def refresh(self) -> Mapping[str, list[dict[str, object]]]:
        """Merge validated appended rows and return compact compatible history."""
        for symbol, ledger in self._ledgers.items():
            rows, cursor = ledger.read_from_cursor(self._cursors[symbol])
            compatible = [
                row for row in rows if execution_row_is_compatible(row, ledger)
            ]
            if compatible:
                merged = [*self._histories[symbol], *compatible]
                self._histories[symbol] = _compact_rows(merged, ledger.run_id)
            self._cursors[symbol] = cursor
        return self._histories


def _compact_rows(
    rows: list[dict[str, object]],
    current_run_id: str,
) -> list[dict[str, object]]:
    book_indices = [
        index
        for index, row in enumerate(rows)
        if row.get("event_type") == "book_observation"
    ]
    if not book_indices:
        return rows
    required = _markout_book_indices(rows, book_indices)
    latest = _latest_current_book_index(rows, book_indices, current_run_id)
    if latest is not None:
        required.add(latest)
    return [
        row
        for index, row in enumerate(rows)
        if row.get("event_type") != "book_observation" or index in required
    ]


def _markout_book_indices(
    rows: list[dict[str, object]],
    book_indices: list[int],
) -> set[int]:
    thresholds = [
        _payload_integer(row, "venue_timestamp_ms") + 5_000
        for row in rows
        if row.get("event_type") == "fill"
    ]
    required: set[int] = set()
    for threshold in thresholds:
        match = next(
            (
                index
                for index in book_indices
                if _payload_integer(rows[index], "exchange_ts_ms") >= threshold
            ),
            None,
        )
        if match is not None:
            required.add(match)
    return required


def _latest_current_book_index(
    rows: list[dict[str, object]],
    book_indices: list[int],
    current_run_id: str,
) -> int | None:
    return next(
        (
            index
            for index in reversed(book_indices)
            if rows[index].get("run_id") == current_run_id
        ),
        None,
    )


def _payload_integer(row: Mapping[str, object], key: str) -> int:
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("asset ledger payload must be an object")
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"asset ledger {key} must be an integer")
    return value
