"""Shared CLI loop for exact report-only HIP-3 breakout observers."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import signal
import threading
import time
from types import FrameType

from hypervector.live.mu_hip3_breakout_shadow import Hip3BreakoutShadowSpec
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3PublicRestSource,
    MuHip3ShadowPollResult,
    MuHip3ShadowPaths,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock


@dataclass(frozen=True)
class ObserverDefaults:
    """Default isolated paths for one exact report-only route."""

    asset: Path
    cohort: Path
    cursor: Path
    journal: Path
    status: Path


@dataclass(frozen=True)
class ObserverConfig:
    """Validated no-authority observer runtime boundaries."""

    paths: MuHip3ShadowPaths
    poll_seconds: float = 5.0
    max_polls: int | None = None
    execution_authority: str = "none"
    report_only: bool = True
    capture_profit_lock_candles: bool = True

    def __post_init__(self) -> None:
        """Reject invalid loops or any attempted authority escalation."""
        if self.poll_seconds <= 0.0:
            raise ValueError("HIP-3 shadow poll_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("HIP-3 shadow max_polls must be positive")
        if self.execution_authority != "none" or self.report_only is not True:
            raise ValueError("HIP-3 shadow observer must remain report-only")
        if not isinstance(self.capture_profit_lock_candles, bool):
            raise ValueError("capture_profit_lock_candles must be boolean")


@dataclass
class _ObserverRuntimeState:
    """Durable lifecycle counters independent of strategy evidence."""

    last_success_observed_at_ms: int | None = None
    last_attempt_observed_at_ms: int | None = None
    consecutive_transient_failures: int = 0
    total_transient_failures: int = 0
    last_transient_failure: dict[str, object] | None = None


def build_parser(defaults: ObserverDefaults) -> argparse.ArgumentParser:
    """Build one standalone public-data observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-ledger", type=Path, default=defaults.asset)
    parser.add_argument("--cohort-ledger", type=Path, default=defaults.cohort)
    parser.add_argument("--cursor", type=Path, default=defaults.cursor)
    parser.add_argument("--journal", type=Path, default=defaults.journal)
    parser.add_argument("--status", type=Path, default=defaults.status)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument(
        "--signal-only",
        action="store_true",
        help="Capture primary signal data without auxiliary profit-lock minute candles",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve explicit CLI arguments into isolated research paths."""
    return ObserverConfig(
        paths=MuHip3ShadowPaths(
            args.asset_ledger,
            args.cohort_ledger,
            args.cursor,
            args.journal,
            args.status,
        ),
        poll_seconds=args.poll_seconds,
        max_polls=args.max_polls,
        capture_profit_lock_candles=not args.signal_only,
    )


def run_observer(
    config: ObserverConfig,
    *,
    runner: MuHip3BreakoutShadowRunner,
    spec: Hip3BreakoutShadowSpec,
    event_type: str = "mu_hip3_breakout_shadow_poll",
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
    stop_reason: Callable[[], str] = lambda: "stop_requested",
) -> int:
    """Capture books and decisions without constructing an order client."""
    state = _restore_runtime_state(config.paths.status)
    polls = 0
    stopped = stop_requested()
    last_observed_ms = state.last_success_observed_at_ms
    while not stopped and not _limit(config, polls):
        observed_ms = clock_ms()
        last_observed_ms = observed_ms
        state.last_attempt_observed_at_ms = observed_ms
        try:
            result = runner.poll(observed_at_ms=observed_ms)
        except TransientCohortMarketDataError as exc:
            _record_transient(state, observed_ms, exc)
            _publish_runtime(config.paths.status, spec, state, "degraded_transient")
        except Exception as exc:
            _publish_runtime(config.paths.status, spec, state, "fault", fatal=exc)
            raise
        else:
            _record_success(state, observed_ms)
            _publish_runtime(config.paths.status, spec, state, "running")
            print(_poll_json(event_type, polls + 1, result), flush=True)
        polls += 1
        stopped = stop_requested()
        if not stopped and not _limit(config, polls):
            sleeper(config.poll_seconds)
    reason = stop_reason() if stopped else "bounded_completion"
    _publish_runtime(
        config.paths.status,
        spec,
        state,
        "stopped",
        stop_reason=reason,
        observed_at_ms=last_observed_ms,
    )
    return 0


def main_for(
    spec: Hip3BreakoutShadowSpec,
    defaults: ObserverDefaults,
    *,
    argv: Sequence[str] | None = None,
) -> int:
    """Run one exact singleton research writer with clean stop handling."""
    config = config_from_args(build_parser(defaults).parse_args(argv))
    stopping = threading.Event()
    received_signal: list[int] = []

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        received_signal.append(signum)
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        runner = MuHip3BreakoutShadowRunner(
            source=MuHip3PublicRestSource(spec),
            paths=config.paths,
            spec=spec,
            capture_profit_lock_candles=config.capture_profit_lock_candles,
        )
        with cohort_checkpoint_runtime_lock(config.paths.status):
            return run_observer(
                config,
                runner=runner,
                spec=spec,
                event_type=f"{_token(spec.symbol)}_hip3_breakout_shadow_poll",
                sleeper=stopping.wait,
                stop_requested=stopping.is_set,
                stop_reason=lambda: _signal_stop_reason(received_signal),
            )
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


def _poll_json(
    event_type: str,
    poll: int,
    result: MuHip3ShadowPollResult,
) -> str:
    payload = {
        "event_type": event_type,
        "execution_authority": "none",
        "report_only": True,
        "poll": poll,
        "bootstrap": result.bootstrap,
        "decisions": len(result.decisions),
        "cursor_decision_time_ms": result.cursor_decision_time_ms,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _limit(config: ObserverConfig, polls: int) -> bool:
    return config.max_polls is not None and polls >= config.max_polls


def _record_transient(
    state: _ObserverRuntimeState,
    observed_at_ms: int,
    error: TransientCohortMarketDataError,
) -> None:
    state.consecutive_transient_failures += 1
    state.total_transient_failures += 1
    state.last_transient_failure = {
        "observed_at_ms": observed_at_ms,
        "source": error.source,
        "reason": error.reason,
    }


def _record_success(state: _ObserverRuntimeState, observed_at_ms: int) -> None:
    state.last_success_observed_at_ms = observed_at_ms
    state.consecutive_transient_failures = 0


def _publish_runtime(
    path: Path,
    spec: Hip3BreakoutShadowSpec,
    state: _ObserverRuntimeState,
    lifecycle: str,
    *,
    stop_reason: str | None = None,
    fatal: Exception | None = None,
    observed_at_ms: int | None = None,
) -> None:
    payload = _load_status(path, spec)
    if state.last_success_observed_at_ms is not None:
        payload["observed_at_ms"] = state.last_success_observed_at_ms
    elif observed_at_ms is not None:
        payload["observed_at_ms"] = observed_at_ms
    payload["observer_runtime"] = {
        "lifecycle": lifecycle,
        "last_success_observed_at_ms": state.last_success_observed_at_ms,
        "last_attempt_observed_at_ms": state.last_attempt_observed_at_ms,
        "consecutive_transient_failures": state.consecutive_transient_failures,
        "total_transient_failures": state.total_transient_failures,
        "last_transient_failure": state.last_transient_failure,
        "stop_reason": stop_reason,
        "fatal_exception_type": None if fatal is None else type(fatal).__name__,
    }
    write_atomic_json(path, payload)


def _load_status(path: Path, spec: Hip3BreakoutShadowSpec) -> dict[str, object]:
    if not path.exists():
        return _base_status(spec)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("execution_authority") != "none":
        raise ValueError("HIP-3 observer status contract is invalid")
    return {str(key): item for key, item in value.items()}


def _base_status(spec: Hip3BreakoutShadowSpec) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": f"{_token(spec.symbol)}_hip3_breakout_shadow_observer",
        "symbol": spec.symbol,
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "execution_authority": "none",
        "report_only": True,
        "signing_client_constructed": False,
        "orders_supported": False,
        "runtime_strategy_changed": False,
    }


def _restore_runtime_state(path: Path) -> _ObserverRuntimeState:
    if not path.exists():
        return _ObserverRuntimeState()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(
        value.get("observer_runtime"), dict
    ):
        return _ObserverRuntimeState()
    runtime = value["observer_runtime"]
    return _ObserverRuntimeState(
        last_success_observed_at_ms=_optional_nonnegative(
            runtime.get("last_success_observed_at_ms")
        ),
        last_attempt_observed_at_ms=_optional_nonnegative(
            runtime.get("last_attempt_observed_at_ms")
        ),
        consecutive_transient_failures=_nonnegative(
            runtime.get("consecutive_transient_failures", 0)
        ),
        total_transient_failures=_nonnegative(
            runtime.get("total_transient_failures", 0)
        ),
        last_transient_failure=_optional_mapping(runtime.get("last_transient_failure")),
    )


def _nonnegative(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("HIP-3 observer runtime counter is invalid")
    return value


def _optional_nonnegative(value: object) -> int | None:
    return None if value is None else _nonnegative(value)


def _optional_mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("HIP-3 observer transient evidence is invalid")
    return dict(value)


def _signal_stop_reason(received: list[int]) -> str:
    if not received:
        return "stop_requested"
    return f"signal_{signal.Signals(received[-1]).name.lower()}"


def _token(symbol: str) -> str:
    if not symbol.startswith("xyz:"):
        raise ValueError("HIP-3 shadow symbol must use the xyz namespace")
    return symbol.removeprefix("xyz:").lower()
