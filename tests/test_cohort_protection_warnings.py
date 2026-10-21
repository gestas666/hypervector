"""Exhausted venue-stop raises surface once per open lifecycle in the checkpoint."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research import cohort_live_checkpoint
from hypervector.research.cohort_live_checkpoint import build_live_checkpoint
from hypervector.research.cohort_protection_warnings import protection_warnings
from test_cohort_live_checkpoint import (
    _GENERATED_AT,
    _RUN_ID,
    _SYMBOLS,
    _active_asset_rows,
)
from test_multi_asset_live_audit import _cohort_rows


def _snapshot(*assets: tuple[str, int | None, float]) -> dict[str, object]:
    return {
        "event_type": "cohort_snapshot",
        "payload": {
            "assets": [
                {"symbol": symbol, "entry_oid": oid, "position_size_signed": size}
                for symbol, oid, size in assets
            ]
        },
    }


def _exhausted(symbol: str, oid: int, at: str) -> dict[str, object]:
    return {
        "event_type": "protective_stop_raise_exhausted",
        "observed_at_utc": at,
        "payload": {
            "symbol": symbol,
            "strategy_id": "test_channel_provider",
            "entry_oid": oid,
            "reason": "protective_stop_raise_exhausted",
            "attempts": 3,
        },
    }


def _attempt(symbol: str, oid: int, raised: bool) -> dict[str, object]:
    return {
        "event_type": "breakeven_stop_attempt",
        "observed_at_utc": "2026-09-24T12:05:00+00:00",
        "payload": {"symbol": symbol, "entry_oid": oid, "raised": raised},
    }


def test_open_unresolved_exhaustion_is_reported_once_with_its_first_time() -> None:
    rows = [
        _exhausted("xyz:CCC", 41, "2026-09-24T12:00:00+00:00"),
        _attempt("xyz:CCC", 41, False),
        _exhausted("xyz:CCC", 41, "2026-09-24T13:00:00+00:00"),
    ]
    snapshot = _snapshot(("xyz:CCC", 41, 2.0), ("BTC", None, 0.0))
    assert protection_warnings(rows, snapshot) == [
        {
            "symbol": "xyz:CCC",
            "strategy_id": "test_channel_provider",
            "entry_oid": 41,
            "reason": "protective_stop_raise_exhausted",
            "observed_at_utc": "2026-09-24T12:00:00+00:00",
        }
    ]


def test_a_later_successful_raise_clears_and_a_new_exhaustion_reopens() -> None:
    snapshot = _snapshot(("SOL", 7, -1.0))
    cleared = [_exhausted("SOL", 7, "a"), _attempt("SOL", 7, True)]
    assert protection_warnings(cleared, snapshot) == []
    reopened = [*cleared, _exhausted("SOL", 7, "b")]
    assert [w["observed_at_utc"] for w in protection_warnings(reopened, snapshot)] == [
        "b"
    ]


@pytest.mark.parametrize(
    "snapshot",
    [
        None,
        _snapshot(("SOL", 7, 0.0)),
        _snapshot(("SOL", 8, 1.0)),
        _snapshot(("ETH", 7, 1.0)),
    ],
)
def test_closed_or_replaced_lifecycles_carry_no_warning(
    snapshot: dict[str, object] | None,
) -> None:
    assert protection_warnings([_exhausted("SOL", 7, "a")], snapshot) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"entry_oid": 7},
        {"symbol": "SOL"},
        {"symbol": "SOL", "entry_oid": True},
        {"symbol": "", "entry_oid": 7},
    ],
)
def test_malformed_break_even_rows_are_refused(payload: dict[str, object]) -> None:
    row = {"event_type": "protective_stop_raise_exhausted", "payload": payload}
    with pytest.raises(ValueError, match="symbol and entry_oid"):
        protection_warnings([row], _snapshot(("SOL", 7, 1.0)))


def _assets() -> dict[str, list[dict[str, object]]]:
    return {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS}


def test_flat_checkpoint_has_no_protection_warnings_key() -> None:
    rows = deepcopy(_cohort_rows())
    envelope = deepcopy(rows[-1])
    exhausted = _exhausted("BTC", 41, str(envelope["observed_at_utc"]))
    envelope.update(
        event_type=exhausted["event_type"],
        sequence=int(envelope["sequence"]) + 1,  # type: ignore[call-overload]
        payload=exhausted["payload"],
    )
    rows.append(envelope)
    checkpoint = build_live_checkpoint(
        rows, _assets(), run_id=_RUN_ID, generated_at=_GENERATED_AT
    )
    assert "protection_warnings" not in checkpoint


def test_checkpoint_publishes_warnings_from_the_selected_run_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = deepcopy(_cohort_rows())
    seen: list[tuple[int, object]] = []
    warning = {
        "symbol": "BTC",
        "strategy_id": "provider",
        "entry_oid": 41,
        "reason": "protective_stop_raise_exhausted",
        "observed_at_utc": "2026-08-01T16:00:05+00:00",
    }

    def project(records: object, snapshot: object) -> list[dict[str, object]]:
        seen.append((len(records), snapshot))  # type: ignore[arg-type]
        return [warning]

    monkeypatch.setattr(cohort_live_checkpoint, "protection_warnings", project)
    checkpoint = build_live_checkpoint(
        rows, _assets(), run_id=_RUN_ID, generated_at=_GENERATED_AT
    )
    latest = [
        row
        for row in rows
        if row["event_type"] == "cohort_snapshot" and row["run_id"] == _RUN_ID
    ][-1]
    assert seen == [(len(rows), latest)]
    assert checkpoint["protection_warnings"] == [warning]
