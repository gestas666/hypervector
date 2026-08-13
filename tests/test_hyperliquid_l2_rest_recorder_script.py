"""Tests for the isolated public REST L2 recorder command."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest
from pytest import CaptureFixture
from requests.exceptions import HTTPError

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent

SCRIPT = Path(__file__).parents[1] / "scripts" / "hyperliquid_l2_rest_recorder.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hyperliquid_l2_rest_recorder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Recorder:
    def __init__(self, outcomes: list[L2SnapshotEvent | Exception]) -> None:
        self.outcomes = outcomes
        self.gaps: list[tuple[int, str]] = []
        self.closed = False
        self.flushes = 0

    def poll(self) -> L2SnapshotEvent:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def declare_gap(self, *, detected_ts_ns: int, reason: str) -> None:
        self.gaps.append((detected_ts_ns, reason))

    def close(self) -> None:
        self.closed = True

    def flush(self) -> None:
        self.flushes += 1


def _event(timestamp_ms: int) -> L2SnapshotEvent:
    level = BookLevel(price=50.0, size=2.0, order_count=1)
    return L2SnapshotEvent(
        "HYPE",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        (level,),
        (level,),
        source="hyperliquid_rest_l2Book_1s",
    )


def test_config_enforces_public_rate_budget_floor() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="at least 0.5"):
        module.RecorderConfig(symbol="HYPE", data_root=Path("data"), poll_seconds=0.49)


def test_bounded_run_is_read_only_and_closes_recorder(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    module = _load_module()
    recorder = _Recorder([_event(1_000), _event(2_000)])
    config = module.RecorderConfig(
        symbol="HYPE",
        data_root=tmp_path,
        poll_seconds=1.0,
        flush_seconds=1.0,
        max_polls=2,
    )

    result = module.run_recorder(
        config,
        recorder=recorder,
        sleeper=lambda _seconds: None,
        monotonic=iter((0.0, 0.0, 1.0, 1.0, 2.0)).__next__,
    )

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert result == 0
    assert recorder.closed is True
    assert recorder.flushes == 2
    assert rows[0]["execution_authority"] == "none"
    assert rows[0]["estimated_request_weight_per_minute"] == 120.0
    assert rows[-1]["event_type"] == "rest_l2_recorder_stopped"
    assert rows[-1]["counts"] == {"attempts": 2, "errors": 0, "snapshots": 2}


def test_http_failure_is_declared_and_recovery_continues(tmp_path: Path) -> None:
    module = _load_module()
    error = HTTPError("429 Too Many Requests")
    response = type("Response", (), {"status_code": 429})()
    error.response = response
    recorder = _Recorder([error, _event(2_000)])
    config = module.RecorderConfig(
        symbol="HYPE",
        data_root=tmp_path,
        poll_seconds=1.0,
        max_polls=2,
    )
    clock = iter((0.0, 0.0, 5.0, 5.0, 10.0))

    module.run_recorder(
        config,
        recorder=recorder,
        sleeper=lambda _seconds: None,
        monotonic=clock.__next__,
        clock_ns=lambda: 123_000_000,
    )

    assert recorder.gaps == [(123_000_000, "http_429")]
    assert recorder.closed is True
