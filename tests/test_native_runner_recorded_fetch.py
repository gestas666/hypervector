"""Recorded acquisition preserves source requests and explicit receipt-time assumptions."""

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch


def _packet(root: Path) -> tuple[Path, str]:
    frame = pd.DataFrame({"timestamp": pd.to_datetime([0], unit="ms", utc=True), "close": [100.0]})
    target = root / "profile_inputs/cold/BTC.parquet"
    target.parent.mkdir(parents=True)
    frame.to_parquet(target, index=False)
    record = {
        "label": "cold",
        "observed_cutoff_utc": "1970-01-01T00:01:00+00:00",
        "elapsed_seconds_with_profiler": 0.0205,
        "fetch_calls": [
            {
                "symbol": "BTC",
                "timeframe": "1m",
                "lookback_days": 14.0,
                "end_ms": 60000,
                "elapsed_seconds": 0.0105,
            }
        ],
        "input_frames": [
            {"symbol": "BTC", "rows": 1, "sha256": sha256(target.read_bytes()).hexdigest()}
        ],
    }
    meta = root / "profile_cold.json"
    meta.write_text(json.dumps(record))
    return meta, sha256(meta.read_bytes()).hexdigest()


def test_recorded_fetch_advances_receipts_and_retains_original_cutoff(tmp_path: Path) -> None:
    """Elapsed samples round upward to milliseconds; request cutoff remains unchanged."""
    path, checksum = _packet(tmp_path)
    clock = ReplayClock(60000)
    fetch = RecordedRunnerFetch(clock)
    fetch.load_packet(path, checksum)
    first = fetch("BTC", "1m", 14.0, end_ms=60000)
    assert clock.now_ms == 60011 and first["close"].tolist() == [100.0]
    fetch.finish_poll()
    assert clock.now_ms == 60021
    assert fetch.completed_packets == 1


@pytest.mark.parametrize(
    "failure", ["checksum", "clock", "request", "incomplete", "extra", "frame"]
)
def test_recorded_fetch_rejects_inconsistent_source_or_consumption(
    tmp_path: Path, failure: str
) -> None:
    """Inputs cannot drift or silently replace missing observations."""
    path, checksum = _packet(tmp_path)
    clock = ReplayClock(60001 if failure == "clock" else 60000)
    fetch = RecordedRunnerFetch(clock)
    if failure == "frame":
        (tmp_path / "profile_inputs/cold/BTC.parquet").write_bytes(b"corrupted")
    if failure in {"checksum", "clock", "frame"}:
        with pytest.raises(ValueError):
            fetch.load_packet(path, "0" * 64 if failure == "checksum" else checksum)
        return
    fetch.load_packet(path, checksum)
    if failure == "incomplete":
        with pytest.raises(ValueError, match="unconsumed"):
            fetch.finish_poll()
    elif failure == "request":
        with pytest.raises(ValueError, match="request"):
            fetch("ETH", "1m", 14.0, end_ms=60000)
    else:
        fetch("BTC", "1m", 14.0, end_ms=60000)
        with pytest.raises(ValueError, match="extra"):
            fetch("BTC", "1m", 14.0, end_ms=60000)


@pytest.mark.parametrize(
    "failure",
    [
        "object",
        "rows",
        "text",
        "naive_clock",
        "fractional_clock",
        "empty_calls",
        "coverage",
        "end_type",
        "end_negative",
        "end_mismatch",
        "lookback_type",
        "lookback_negative",
        "lookback_nan",
        "elapsed_type",
        "elapsed_negative",
        "elapsed_nan",
        "elapsed_exceeds_poll",
        "duplicate_frame",
        "frame_rows",
        "frame_rows_bool",
        "frame_escape",
    ],
)
def test_recorded_metadata_validation_precedes_clock_changes(tmp_path: Path, failure: str) -> None:
    """Even authenticated malformed metadata must fail atomically before runner time advances."""
    path, _ = _packet(tmp_path)
    record = json.loads(path.read_text())
    record = _invalid_record(record, failure)
    path.write_text(json.dumps(record))
    clock = ReplayClock(60000)
    fetch = RecordedRunnerFetch(clock)
    with pytest.raises(ValueError):
        fetch.load_packet(path, sha256(path.read_bytes()).hexdigest())
    assert clock.now_ms == 60000 and fetch.completed_packets == 0
    with pytest.raises(ValueError, match="no active packet"):
        fetch.finish_poll()


def test_packet_lifecycle_cannot_be_replaced_or_finished_twice(tmp_path: Path) -> None:
    """Request consumption and processing time belong to one packet only."""
    path, checksum = _packet(tmp_path)
    fetch = RecordedRunnerFetch(ReplayClock(60000))
    with pytest.raises(ValueError, match="no active packet"):
        fetch("BTC", "1m", 14.0, end_ms=60000)
    fetch.load_packet(path, checksum)
    with pytest.raises(ValueError, match="unfinished"):
        fetch.load_packet(path, checksum)
    fetch("BTC", "1m", 14.0, end_ms=60000)
    fetch.finish_poll()
    with pytest.raises(ValueError, match="no active packet"):
        fetch.finish_poll()


def test_future_packet_can_be_scheduled_but_not_consumed_early(tmp_path: Path) -> None:
    """Runner reconciliation can precede acquisition without exposing future candles."""
    path, checksum = _packet(tmp_path)
    clock = ReplayClock(59000)
    fetch = RecordedRunnerFetch(clock)
    fetch.load_packet(path, checksum)
    with pytest.raises(ValueError, match="request clock"):
        fetch("BTC", "1m", 14.0, end_ms=60000)
    assert clock.now_ms == 59000
    clock.advance_to(60000)
    assert fetch("BTC", "1m", 14.0, end_ms=60000)["close"].tolist() == [100.0]
    fetch.finish_poll()


def _invalid_record(record: dict[str, object], failure: str) -> object:
    call = record["fetch_calls"][0]
    changes = {
        "end_type": ("end_ms", True),
        "end_negative": ("end_ms", -1),
        "end_mismatch": ("end_ms", 60001),
        "lookback_type": ("lookback_days", "14"),
        "lookback_negative": ("lookback_days", -1),
        "lookback_nan": ("lookback_days", float("nan")),
        "elapsed_type": ("elapsed_seconds", True),
        "elapsed_negative": ("elapsed_seconds", -1),
        "elapsed_nan": ("elapsed_seconds", float("nan")),
        "elapsed_exceeds_poll": ("elapsed_seconds", 1),
    }
    if failure in changes:
        key, value = changes[failure]
        call[key] = value
    elif failure == "object":
        record = []
    elif failure == "rows":
        record["fetch_calls"] = {}
    elif failure == "text":
        call["symbol"] = ""
    elif failure == "naive_clock":
        record["observed_cutoff_utc"] = "1970-01-01T00:01:00"
    elif failure == "fractional_clock":
        record["observed_cutoff_utc"] = "1970-01-01T00:01:00.000001+00:00"
    elif failure == "empty_calls":
        record["fetch_calls"] = []
    elif failure == "coverage":
        call["symbol"] = "ETH"
    elif failure == "duplicate_frame":
        record["input_frames"] *= 2
    elif failure == "frame_rows":
        record["input_frames"][0]["rows"] = 2
    elif failure == "frame_rows_bool":
        record["input_frames"][0]["rows"] = True
    elif failure == "frame_escape":
        record["label"] = "../../outside"
    return record
