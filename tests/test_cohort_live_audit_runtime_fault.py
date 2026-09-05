"""Runtime-fault coverage for immutable cohort live audits."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from test_multi_asset_live_audit import (
    _RUN_ID,
    _SYMBOLS,
    _asset_rows,
    _cohort_rows,
    _row,
)


def test_runtime_fault_is_counted_in_audit_health() -> None:
    """A terminal cohort runtime fault must not look healthy in the audit."""
    rows = _cohort_rows()
    rows.append(
        _row(
            len(rows) + 1,
            "runtime_fault",
            {
                "status": "faulted",
                "exception_type": "ValueError",
                "orders_attempted": False,
            },
        )
    )

    report = audit_multi_asset_live_run(
        rows,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
    )

    assert report["health"]["faults"] == 1
    assert report["health"]["runtime"] == {
        "faults": 1,
        "latest_fault": {
            "exception_type": "ValueError",
            "observed_at_utc": rows[-1]["observed_at_utc"],
            "orders_attempted": False,
        },
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "status": "running",
                "exception_type": "ValueError",
                "orders_attempted": False,
            },
            "status must be faulted",
        ),
        (
            {"status": "faulted", "exception_type": "", "orders_attempted": False},
            "exception_type must be non-empty text",
        ),
        (
            {
                "status": "faulted",
                "exception_type": "ValueError",
                "orders_attempted": 0,
            },
            "orders_attempted must be boolean",
        ),
    ],
)
def test_malformed_runtime_fault_fails_audit(
    payload: dict[str, object], message: str
) -> None:
    """Malformed terminal-fault evidence must fail instead of looking healthy."""
    rows = _cohort_rows()
    rows.append(_row(len(rows) + 1, "runtime_fault", payload))

    with pytest.raises(ValueError, match=message):
        audit_multi_asset_live_run(
            rows,
            {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
        )
