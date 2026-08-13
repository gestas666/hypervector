"""CLI safety contracts for the four-Pine forward observer."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/pine_stack_forward_observer.py")


def _module() -> ModuleType:
    """Load the observer script without packaging the scripts directory."""
    spec = spec_from_file_location("pine_stack_forward_observer_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Pine observer: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_defaults_pin_eth_30m_zero_capital_forward_ledger() -> None:
    """The observer defaults to the tested asset/timeframe and isolated ledger."""
    args = _module().build_parser().parse_args([])

    assert args.symbol == "ETH"
    assert args.bar_minutes == 30
    assert args.ledger == Path("data/research/forward/pine_stack_eth30/decisions.jsonl")
    assert args.lookback_days == 7


def test_observer_command_has_no_live_or_submit_surface() -> None:
    """No command-line option can arm or place an order."""
    parser = _module().build_parser()
    options = {option for action in parser._actions for option in action.option_strings}
    source = _SCRIPT.read_text(encoding="utf-8")

    assert "--enabled" not in options
    assert "--live" not in options
    assert "--submit" not in options
    assert "private_key" not in source
    assert "submit_order" not in source
