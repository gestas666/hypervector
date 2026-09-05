"""Continuous zero-authority monitor contracts for the SOL forward replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.sol_route_native_one_blocker_shadow import (
    SolFundingEvidence,
)
import hypervector.research.sol_route_native_one_blocker_monitor as monitor


def test_once_uses_lagged_archive_cutoff() -> None:
    """A poll excludes the recorder's still-unflushed tail."""
    calls: list[dict[str, object]] = []
    spec = _spec()

    def snapshot(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {"status": "waiting_future_exact_candidate"}

    result = monitor.run_sol_route_native_monitor(
        spec=spec,
        once=True,
        interval_seconds=120.0,
        archive_lag_seconds=60.0,
        clock_ms=lambda: 2_000_000,
        funding_fetcher=_funding,
        snapshot_runner=snapshot,
        sleep_fn=lambda _: None,
    )

    assert result == 0
    assert calls[0]["observed_at_ms"] == 1_940_000
    assert calls[0]["capture_start_ms"] == spec.capture_start_ms
    assert calls[0]["source_run_id"] == spec.source_run_id


def test_failed_once_preserves_last_good_snapshot(tmp_path: Path) -> None:
    """A technical refresh failure cannot overwrite prior valid evidence."""
    output = tmp_path / "latest.json"
    output.write_text('{"status":"last-good"}\n', encoding="utf-8")
    spec = _spec(output=output)

    def fail(**_: object) -> dict[str, object]:
        raise ValueError("funding unavailable")

    result = monitor.run_sol_route_native_monitor(
        spec=spec,
        once=True,
        interval_seconds=120.0,
        archive_lag_seconds=60.0,
        clock_ms=lambda: 2_000_000,
        funding_fetcher=_funding,
        snapshot_runner=fail,
        sleep_fn=lambda _: None,
    )

    assert result == 2
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "last-good"}


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_monitor_rejects_invalid_interval(value: float) -> None:
    """Invalid cadence values fail before any evidence read or sleep."""
    with pytest.raises(ValueError, match="finite and positive"):
        monitor.run_sol_route_native_monitor(
            spec=_spec(),
            once=True,
            interval_seconds=value,
            archive_lag_seconds=60.0,
            clock_ms=lambda: 2_000_000,
            funding_fetcher=_funding,
            snapshot_runner=lambda **_: {},
            sleep_fn=lambda _: None,
        )


def _spec(*, output: Path = Path("latest.json")) -> object:
    return monitor.SolRouteNativeMonitorSpec(
        config_path=Path("v51.toml"),
        cohort_ledger=Path("cohort.jsonl"),
        asset_ledger=Path("sol.jsonl"),
        data_root=Path("data"),
        source_run_id="run-v51",
        capture_start_ms=1_000_000,
        output=output,
    )


def _funding(start_ms: int, end_ms: int) -> SolFundingEvidence:
    return SolFundingEvidence(start_ms, end_ms, ())
