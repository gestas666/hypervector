"""CLI contract tests for the four-Pine 15m/30m development screen."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/pine_stack_15m_30m_screen.py")


def _module() -> ModuleType:
    """Load the report-only script without making scripts an import package."""
    spec = spec_from_file_location("pine_stack_screen_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Pine stack screen: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_inputs_pin_four_assets_and_verified_funding() -> None:
    """The experiment must not silently substitute assets or funding sources."""
    script = _module()
    inputs = script.default_asset_inputs(Path("data"))

    assert [value.symbol for value in inputs] == ["BTC", "ETH", "SOL", "HYPE"]
    assert [value.venue_max_leverage for value in inputs] == [40.0, 25.0, 20.0, 10.0]
    assert all(value.bars_path.name.endswith("_1m_365d.parquet") for value in inputs)
    assert all(value.funding_path.name == "funding.parquet" for value in inputs)


def test_cli_defaults_to_immutable_development_control() -> None:
    """The default command must remain report-only and development-scoped."""
    script = _module()
    args = script.build_parser().parse_args([])

    assert args.run_id == "pine_stack_15m_30m_development_v1"
    assert args.output == Path(
        "data/logs/research/pine_stack_15m_30m_development_v1.json"
    )
    assert args.journal == Path("data/research/strategy_trials.duckdb")
