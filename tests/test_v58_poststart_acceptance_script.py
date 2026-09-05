"""CLI contract for immutable V58 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path("scripts/v58_poststart_acceptance.py")


def test_v58_parser_binds_exact_config_stress_and_preflight() -> None:
    """The publisher must bind V58 inputs and its 15-second pressure contract."""
    assert _SCRIPT.is_file(), "V58 post-start publisher is missing"
    spec = spec_from_file_location("v58_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name == (
        "multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
    )
    assert args.stress.name == ("v58_eight_asset_growth_sizing_stress_20260819_v1.json")
    assert args.preflight == Path("flat.json")
    assert args.maximum_pressure_age_seconds == 15.0


def test_v58_generator_identity_covers_direct_verdict_dependencies() -> None:
    """Immutable output must change when a verdict-capable dependency changes."""
    spec = spec_from_file_location("v58_poststart_identity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {path.name for path in module._SPEC.generator_files}

    assert {
        "cohort_live_audit_values.py",
        "cohort_startup_pressure_acceptance.py",
        "multi_asset_live_config.py",
        "v52_poststart_acceptance.py",
    }.issubset(names)
