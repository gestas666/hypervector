"""Pressure-provenance checks for the HIP-3 fresh15 journal provider."""

from pathlib import Path

import pandas as pd
import pytest

from test_hip3_fresh15_journal_provider import (
    _CLOSE_MS,
    _bars,
    _collector,
    _decision,
    _journal,
)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pressure_source", "other_venue", "pressure source"),
        ("pressure_exchange_ts_ms", _CLOSE_MS + 1, "pressure timestamps"),
        ("pressure_recv_ts_ms", _CLOSE_MS + 3_001, "pressure timestamps"),
    ],
)
def test_pressure_provenance_must_be_exact(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    """Success-shaped evidence cannot hide a wrong source or impossible time."""
    path = tmp_path / "sp500.jsonl"
    row = _decision("xyz:SP500")
    row["decision"][field] = value
    _journal(path, row)

    with pytest.raises(ValueError, match=message):
        _collector(path)(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )
