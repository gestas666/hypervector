"""Tests for the preregistered SOL decision-latency surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_range_onset_event_replay.py"
)


def _module() -> ModuleType:
    spec = spec_from_file_location("range_onset_latency_surface", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPT.parent))
    return module


def test_latency_surface_is_frozen_at_forward_observer_quantiles() -> None:
    """Both candidate stops must face zero, median, and p95-like delays."""
    module = _module()

    trials = module.latency_trial_grid()

    assert len(trials) == 6
    assert {
        (trial.stop_bps, trial.margin_fraction, trial.leverage, trial.decision_delay_ms)
        for trial in trials
    } == {
        (stop, 0.03, 5.0, delay)
        for stop in (60.0, 80.0)
        for delay in (0, 8_000, 16_000)
    }


def test_event_config_carries_trial_delay_into_replay() -> None:
    """A latency trial must not collapse back to the zero-delay default."""
    module = _module()
    trial = module.EventTrial(80.0, 0.03, 5.0, 16_000)

    config = module._event_config(trial)

    assert config.stop_bps == pytest.approx(80.0)
    assert config.margin_fraction == pytest.approx(0.03)
    assert config.leverage == pytest.approx(5.0)
    assert config.decision_delay_ms == 16_000
