"""Durable lifecycle and transient-failure contracts for HIP-3 observers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.hip3_breakout_shadow_observer import (
    ObserverConfig,
    run_observer,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.mu_hip3_breakout_shadow import MU_SHADOW_SPEC
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3ShadowPaths,
    MuHip3ShadowPollResult,
)


class _Runner:
    """Return or raise a deterministic sequence of poll outcomes."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.attempts = 0

    def poll(self, *, observed_at_ms: int) -> MuHip3ShadowPollResult:
        """Consume one configured outcome for the supplied observation time."""
        self.attempts += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert outcome == "success"
        return MuHip3ShadowPollResult((), False, observed_at_ms, 900_000, 0)


def _config(tmp_path: Path, *, max_polls: int) -> ObserverConfig:
    paths = MuHip3ShadowPaths(
        asset_ledger=tmp_path / "xyz:mu.jsonl",
        cohort_ledger=tmp_path / "unused.jsonl",
        cursor=tmp_path / "cursor.json",
        journal=tmp_path / "journal.jsonl",
        status=tmp_path / "status.json",
    )
    return ObserverConfig(paths=paths, poll_seconds=1.0, max_polls=max_polls)


def test_transient_failure_is_durable_and_next_poll_recovers(tmp_path: Path) -> None:
    """A classified public-read failure cannot silently terminate collection."""
    config = _config(tmp_path, max_polls=2)
    runner = _Runner(
        [
            TransientCohortMarketDataError(
                source="hyperliquid_public_l2",
                reason="transport_timeout_retry_exhausted",
            ),
            "success",
        ]
    )
    clocks = iter((1_000, 2_000))
    degraded: list[dict[str, object]] = []

    def capture_degraded(_seconds: float) -> None:
        degraded.append(json.loads(config.paths.status.read_text()))

    result = run_observer(
        config,
        runner=runner,
        spec=MU_SHADOW_SPEC,
        clock_ms=lambda: next(clocks),
        sleeper=capture_degraded,
    )

    assert result == 0
    assert runner.attempts == 2
    runtime = degraded[0]["observer_runtime"]
    assert runtime["lifecycle"] == "degraded_transient"
    assert runtime["last_success_observed_at_ms"] is None
    assert runtime["last_attempt_observed_at_ms"] == 1_000
    assert runtime["consecutive_transient_failures"] == 1
    assert runtime["last_transient_failure"] == {
        "observed_at_ms": 1_000,
        "reason": "transport_timeout_retry_exhausted",
        "source": "hyperliquid_public_l2",
    }
    status = json.loads(config.paths.status.read_text())
    assert status["observed_at_ms"] == 2_000
    assert status["observer_runtime"]["lifecycle"] == "stopped"
    assert status["observer_runtime"]["stop_reason"] == "bounded_completion"
    assert status["observer_runtime"]["last_attempt_observed_at_ms"] == 2_000
    assert status["observer_runtime"]["total_transient_failures"] == 1


def test_nontransient_fault_is_durable_and_propagates(tmp_path: Path) -> None:
    """A parse or schema defect remains fatal instead of being retry-shaped."""
    config = _config(tmp_path, max_polls=1)
    runner = _Runner([ValueError("malformed public candle schema")])

    with pytest.raises(ValueError, match="malformed public candle schema"):
        run_observer(
            config,
            runner=runner,
            spec=MU_SHADOW_SPEC,
            clock_ms=lambda: 3_000,
            sleeper=lambda _seconds: None,
        )

    status = json.loads(config.paths.status.read_text())
    runtime = status["observer_runtime"]
    assert runtime["lifecycle"] == "fault"
    assert runtime["fatal_exception_type"] == "ValueError"
    assert runtime["last_success_observed_at_ms"] is None
    assert status["execution_authority"] == "none"
    assert status["report_only"] is True


def test_signal_stop_is_durable_without_rewriting_last_success(tmp_path: Path) -> None:
    """A clean signal stop must be distinguishable from a stale running process."""
    config = _config(tmp_path, max_polls=2)
    runner = _Runner(["success"])
    stop_checks = iter((False, True))

    result = run_observer(
        config,
        runner=runner,
        spec=MU_SHADOW_SPEC,
        clock_ms=lambda: 4_000,
        sleeper=lambda _seconds: None,
        stop_requested=lambda: next(stop_checks),
        stop_reason=lambda: "signal_sigterm",
    )

    assert result == 0
    status = json.loads(config.paths.status.read_text())
    runtime = status["observer_runtime"]
    assert runtime["lifecycle"] == "stopped"
    assert runtime["stop_reason"] == "signal_sigterm"
    assert runtime["last_success_observed_at_ms"] == 4_000
    assert status["observed_at_ms"] == 4_000
