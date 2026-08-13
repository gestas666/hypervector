"""CLI contract tests for the complete low-timeframe research matrix."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/low_tf_multi_asset_screen.py")


def _module() -> ModuleType:
    """Load the research script without making scripts an import package."""
    spec = spec_from_file_location("low_tf_multi_asset_screen_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load low-timeframe screen: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_inputs_pin_all_native_assets_and_year_matched_funding() -> None:
    script = _module()
    inputs = script.default_asset_inputs(Path("data"))

    assert [value.symbol for value in inputs] == ["BTC", "ETH", "SOL", "HYPE"]
    assert [value.venue_max_leverage for value in inputs] == [40.0, 25.0, 20.0, 10.0]
    assert all(value.bars_path.name.endswith("_1m_365d.parquet") for value in inputs)
    assert all(
        "20250728T000000000000Z_20260728T000000000000Z_funding"
        in str(value.funding_paths[0])
        for value in inputs
    )


def test_cli_defaults_to_report_only_development_matrix() -> None:
    script = _module()
    args = script.build_parser().parse_args([])

    assert args.segment == "development"
    assert args.run_id == "low_tf_multi_asset_development_v1"
    assert args.output == Path(
        "data/logs/research/low_tf_multi_asset_development_v1.json"
    )
    assert args.journal == Path("data/research/strategy_trials.duckdb")
