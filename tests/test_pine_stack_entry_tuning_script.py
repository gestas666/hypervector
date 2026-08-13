"""CLI safety contracts for four-Pine entry parameter tuning."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/pine_stack_entry_tuning.py")


def _module() -> ModuleType:
    """Load the report-only script without packaging the scripts directory."""
    spec = spec_from_file_location("pine_stack_entry_tuning_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Pine stack tuner: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_defaults_pin_eth_30m_development_and_immutable_outputs() -> None:
    """The first tuning phase must match the frozen Stage-A survivor."""
    args = _module().build_parser().parse_args([])

    assert args.symbol == "ETH"
    assert args.bar_minutes == 30
    assert args.segment == "development"
    assert args.surface == "entry_v1"

    choices = next(
        action.choices
        for action in _module().build_parser()._actions
        if action.dest == "surface"
    )
    assert set(choices) == {
        "entry_v1",
        "risk_hold_v1",
        "tp_support_v1",
        "tp_axis_threshold_v1",
        "final_interaction_v1",
        "frozen_validation_v1",
        "frozen_pseudo_holdout_v1",
        "post_hoc_exit_diagnostic_v1",
    }
    assert args.run_id == "pine_stack_eth30_entry_tuning_development_v1"
    assert args.output == Path(
        "data/logs/research/pine_stack_eth30_entry_tuning_development_v1.json"
    )
    assert args.journal == Path("data/research/strategy_trials.duckdb")


def test_validation_allows_only_the_pre_frozen_surface() -> None:
    """Untouched validation cannot reopen a development tuning grid."""
    module = _module()

    module._validate_protocol("frozen_validation_v1", "validation")
    with pytest.raises(ValueError, match="frozen_validation_v1"):
        module._validate_protocol("entry_v1", "validation")


def test_pseudo_holdout_allows_only_the_validation_winner() -> None:
    """The last segment is sealed to one identity before it is read."""
    module = _module()

    module._validate_protocol("frozen_pseudo_holdout_v1", "pseudo_holdout")
    with pytest.raises(ValueError, match="frozen_pseudo_holdout_v1"):
        module._validate_protocol("frozen_validation_v1", "pseudo_holdout")


def test_post_hoc_diagnostic_is_explicitly_allowed_but_not_validation() -> None:
    """Contaminated analysis is named consistently in every historical segment."""
    module = _module()

    for segment in ("development", "validation", "pseudo_holdout"):
        module._validate_protocol("post_hoc_exit_diagnostic_v1", segment)


def test_tuning_command_has_no_live_execution_surface() -> None:
    """Parameter research cannot accidentally grow live-order authority."""
    source = _SCRIPT.read_text(encoding="utf-8")

    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
