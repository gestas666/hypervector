"""Public context capture must preserve fields, gaps and durable history."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import hypervector.research.hip3_context_history as history
from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader
from test_hip3_roster_funding import _Info


def _response() -> list[object]:
    return [
        {"universe": [{"name": "xyz:EXTRA"}, {"name": "xyz:SNDK"}]},
        [
            {"funding": "0", "premium": None, "oraclePx": "10", "markPx": "10.1"},
            {
                "funding": "-0.0001",
                "premium": "0.002",
                "oraclePx": "100",
                "markPx": "100.2",
            },
        ],
    ]


def test_capture_preserves_entire_public_universe_with_one_request(
    tmp_path: Path,
) -> None:
    """Research gets unrostered markets without adding endpoint requests."""
    info = _Info(_response())
    reader = Hip3RosterFundingReader(info=info, symbols=("xyz:SNDK",))
    assert hasattr(reader, "snapshot_with_capture")
    rates = reader.snapshot_with_capture(tmp_path)
    rows = [
        json.loads(line)
        for p in tmp_path.glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    assert rates == {"xyz:SNDK": -0.0001}
    assert len(info.calls) == 1
    assert len(rows) == 1
    by_symbol = {row["symbol"]: row for row in rows[0]["markets"]}
    assert by_symbol["xyz:SNDK"]["premium"] == 0.002
    assert by_symbol["xyz:SNDK"]["oracle_price"] == 100.0
    assert by_symbol["xyz:SNDK"]["mark_price"] == 100.2
    assert by_symbol["xyz:EXTRA"]["premium"] is None
    assert rows[0]["execution_authority"] == "none"
    assert rows[0]["timestamp_source"] == "local_receipt"


def test_capture_retains_history_across_reader_restarts(tmp_path: Path) -> None:
    """Independent reader lifetimes append instead of replacing earlier observations."""
    for _ in range(2):
        reader = Hip3RosterFundingReader(info=_Info(_response()), symbols=("xyz:SNDK",))
        assert hasattr(reader, "snapshot_with_capture")
        reader.snapshot_with_capture(tmp_path)
    rows = [
        json.loads(line)
        for p in tmp_path.glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    assert len(rows) == 2
    assert rows[0]["observed_at_utc"] <= rows[1]["observed_at_utc"]


@pytest.mark.parametrize(
    "field,value", [("premium", "nan"), ("oraclePx", "0"), ("markPx", "inf")]
)
def test_invalid_context_does_not_publish_success(
    tmp_path: Path, field: str, value: str
) -> None:
    """Invalid prices and nonfinite premiums cannot enter the historical dataset."""
    response = _response()
    response[1][1][field] = value
    reader = Hip3RosterFundingReader(info=_Info(response), symbols=("xyz:SNDK",))
    assert hasattr(reader, "snapshot_with_capture")
    with pytest.raises(ValueError):
        reader.snapshot_with_capture(tmp_path)
    assert not list(tmp_path.glob("*.jsonl"))


def test_incomplete_tail_is_not_silently_overwritten(tmp_path: Path) -> None:
    """Crash damage stays intact and forces an actionable storage failure."""
    path = tmp_path / (datetime.now(UTC).date().isoformat() + ".jsonl")
    path.write_text('{"partial":')
    reader = Hip3RosterFundingReader(info=_Info(_response()), symbols=("xyz:SNDK",))
    assert hasattr(reader, "snapshot_with_capture")
    with pytest.raises(ValueError, match="incomplete.*tail"):
        reader.snapshot_with_capture(tmp_path)
    assert path.read_text() == '{"partial":'


def test_one_unparseable_market_does_not_blank_the_whole_universe(
    tmp_path: Path,
) -> None:
    """The roster covers 6 markets; the dex carries ~123. One bad row is not an outage.

    Raising here turned a parse failure on a market nobody trades into an
    unavailable roster checkpoint, which is the only HIP-3 fee evidence the live
    supervisor has.
    """
    response = [
        {
            "universe": [
                {"name": "xyz:SNDK", "growthMode": True, "maxLeverage": 10},
                {"name": "xyz:JUNK", "growthMode": True, "maxLeverage": 10},
            ]
        },
        [
            {"funding": "0.0001", "oraclePx": "10.0", "markPx": "10.0"},
            {"funding": "0.0001", "oraclePx": "not-a-number", "markPx": "10.0"},
        ],
    ]

    record = history.context_record(
        response, dex="xyz", observed_at=datetime(2026, 9, 22, tzinfo=UTC)
    )

    markets = {row["symbol"]: row for row in record["markets"]}
    assert record["status"] == "available"
    assert markets["xyz:SNDK"]["oracle_price"] == 10.0
    assert markets["xyz:JUNK"]["parse_error"]
    assert record["unparsed_market_count"] == 1


def test_retention_prunes_day_files_beyond_the_window(tmp_path: Path) -> None:
    """Unbounded capture added ~24 MB/day to the volume the live system shares."""
    for day in (10, 9, 1):
        history.append_context_record(
            tmp_path,
            history.unavailable_context_record(
                datetime(2026, 9, day, tzinfo=UTC), "ServerError"
            ),
        )

    history.prune_context_history(
        tmp_path, retention_days=3, now=datetime(2026, 9, 11, tzinfo=UTC)
    )

    remaining = sorted(path.name for path in tmp_path.glob("*.jsonl"))
    assert remaining == ["2026-09-09.jsonl", "2026-09-10.jsonl"]
