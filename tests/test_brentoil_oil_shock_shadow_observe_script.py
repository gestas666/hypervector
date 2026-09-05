"""Standalone BRENTOIL oil-shock observer command tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from hypervector.live.brentoil_oil_shock_shadow_runner import (
    BrentoilOilShockShadowPollResult,
)


class _Runner:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def poll(self, *, observed_at_ms: int) -> BrentoilOilShockShadowPollResult:
        self.calls.append(observed_at_ms)
        return BrentoilOilShockShadowPollResult(
            (), not self.calls[:-1], observed_at_ms, 0, 0
        )


def test_defaults_are_isolated_report_only_paths() -> None:
    """The command cannot silently attach to v51 ledgers or configs."""
    script = _script()

    config = script.config_from_args(script.build_parser().parse_args([]))

    assert config.execution_authority == "none"
    assert config.report_only is True
    assert "brentoil_oil_shock_shadow" in str(config.paths.book_ledger)
    assert "brentoil_oil_shock_shadow" in str(config.paths.candle_ledger)
    assert "bidirectional_cohort" not in str(config.paths.book_ledger)
    assert config.paths.websocket_archive != config.paths.rest_mark_archive


def test_bounded_loop_polls_without_execution_surface() -> None:
    """A bounded observer exits after the requested public-data polls."""
    script = _script()
    args = script.build_parser().parse_args(["--max-polls", "2"])
    config = script.config_from_args(args)
    runner = _Runner()
    ticks = iter((100, 200))

    polls = script.run_observer(
        config,
        runner=runner,
        clock_ms=lambda: next(ticks),
        sleeper=lambda _seconds: None,
    )

    assert polls == 2
    assert runner.calls == [100, 200]


def _script() -> ModuleType:
    path = Path("scripts/brentoil_oil_shock_shadow_observe.py")
    spec = importlib.util.spec_from_file_location("brentoil_shadow_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("BRENTOIL oil-shock observer script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
