"""CLI contract for immutable V59 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path("scripts/v59_poststart_acceptance.py")


def test_v59_parser_binds_candidate_stress_and_preflight() -> None:
    """The publisher must bind candidate inputs and 15-second pressure."""
    assert _SCRIPT.is_file(), "V59 post-start publisher is missing"
    spec = spec_from_file_location("v59_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name.endswith("sp500_short_containment_candidate_v59.toml")
    assert args.stress.name.startswith("v59_sp500_short_containment_growth_stress_")
    assert args.preflight == Path("flat.json")
    assert args.maximum_pressure_age_seconds == 15.0


def test_v59_generator_identity_covers_verdict_dependencies() -> None:
    """Immutable output must bind every direct verdict-capable dependency."""
    spec = spec_from_file_location("v59_poststart_identity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {path.name for path in module._SPEC.generator_files}

    assert {
        "cohort_configuration_exit_policy.py",
        "cohort_live_audit_values.py",
        "cohort_startup_pressure_acceptance.py",
        "multi_asset_live_config.py",
        "v59_poststart_acceptance.py",
    }.issubset(names)
