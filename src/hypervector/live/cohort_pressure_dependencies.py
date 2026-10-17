"""Owned lifecycle for the exact unsigned pressure sources a cohort requires."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from functools import partial
import json
from pathlib import Path
import sys
import time

from hypervector.live.cohort_dependency_supervision import (
    start_owned_dependency,
    stop_owned_dependency,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    HIP3_SNDK_FRESH15_V4_STRATEGY,
    require_fresh_index_observer,
)
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError
from hypervector.live.hip3_fresh15_journal_contracts import DEFAULT_OBSERVER_STATES
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
)

_STARTUP_TIMEOUT_SECONDS = 120.0
_HEALTH_POLL_SECONDS = 2.0


def pressure_dependency_commands(
    config: MultiAssetLiveConfig,
) -> dict[str, tuple[str, ...]]:
    """Return only unsigned observers required by the configured provider identities."""
    strategies = {provider.strategy_id for provider in config.providers}
    symbols = set()
    if HIP3_INDEX_FRESH15_V3_STRATEGY in strategies:
        symbols.update(("xyz:SP500", "xyz:SPCX"))
    if SPCX_CASH_SESSION_LONG_STRATEGY in strategies:
        symbols.add("xyz:SPCX")
    output = {
        symbol: (
            sys.executable,
            "-m", "hypervector.operations.index_hip3_breakout_shadow_observe",
            "--symbol",
            symbol,
        )
        for symbol in sorted(symbols)
    }
    if HIP3_SNDK_FRESH15_V4_STRATEGY in strategies:
        output["xyz:SNDK"] = (
            sys.executable,
            "-m", "hypervector.operations.sndk_hip3_breakout_shadow_observe",
        )
        if _spcx_signal_only(config, strategies):
            output["xyz:SPCX"] += ("--signal-only",)
    return output


def _spcx_signal_only(config: MultiAssetLiveConfig, strategies: set[str]) -> bool:
    if SPCX_CASH_SESSION_LONG_STRATEGY not in strategies:
        return False
    plans = [
        provider.execution_for("xyz:SPCX", side)
        for provider in config.providers
        if "xyz:SPCX" in provider.execution_symbols
        for side in provider.executable_sides("xyz:SPCX")
    ]
    return bool(plans) and all(plan.profit_lock_policy == "none" for plan in plans)


def run_pressure_dependencies(
    config: MultiAssetLiveConfig,
    *,
    log_root: Path,
    stop_requested: Callable[[], bool],
) -> None:
    """Reuse healthy sources and clean up owned children on stop or startup failure."""
    commands = pressure_dependency_commands(config)
    unavailable: dict[str, str] = {}
    with ExitStack() as cleanup:
        owned = []
        for symbol, command in commands.items():
            process = start_owned_dependency(
                command,
                config,
                timeout_seconds=_STARTUP_TIMEOUT_SECONDS,
                log_path=log_root / f"{symbol.replace(':', '_').lower()}.log",
                health_check=partial(_require_symbol_health, symbol),
            )
            if process is not None:
                owned.append(process)
                cleanup.callback(stop_owned_dependency, process)
        while not stop_requested():
            for process in owned:
                if process.poll() is not None:
                    raise MultiAssetLiveConfigError(
                        "unsigned pressure dependency exited; inspect its observer log"
                    )
            for symbol in commands:
                _observe_symbol_health(symbol, config, unavailable)
            time.sleep(_HEALTH_POLL_SECONDS)


def _require_symbol_health(symbol: str, config: MultiAssetLiveConfig) -> None:
    require_fresh_index_observer(symbol, datetime.now(UTC))
    if symbol not in {"xyz:SP500", "xyz:SPCX"}:
        return
    command = pressure_dependency_commands(config)[symbol]
    expected_capture = "--signal-only" not in command
    status = json.loads(DEFAULT_OBSERVER_STATES[symbol][0].read_text(encoding="utf-8"))
    if status.get("profit_lock_capture_enabled", True) is not expected_capture:
        raise MultiAssetLiveConfigError(
            f"{symbol} observer capture mode differs from the configured dependency; "
            "stop the existing unsigned observer and relaunch the dependency command"
        )


def _observe_symbol_health(
    symbol: str, config: MultiAssetLiveConfig, unavailable: dict[str, str]
) -> None:
    try:
        _require_symbol_health(symbol, config)
    except Hip3ObserverUnavailableError as error:
        if error.reason == "observer_runtime_not_running":
            raise
        if unavailable.get(symbol) != error.reason:
            _health_event(symbol, "unavailable", error.reason)
        unavailable[symbol] = error.reason
    else:
        if symbol in unavailable:
            _health_event(symbol, "recovered", unavailable.pop(symbol))


def _health_event(symbol: str, status: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "event_type": "unsigned_pressure_dependency_health",
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "symbol": symbol,
                "status": status,
                "reason": reason,
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        flush=True,
    )
