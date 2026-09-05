"""Publication boundary for immutable v52 technical acceptance."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v52_poststart_acceptance.py")


def test_v52_parser_binds_exact_stress_and_requires_flat_preflight() -> None:
    """The report command must be incapable of arming live execution."""
    if not _SCRIPT.exists():
        pytest.fail("v52 post-start acceptance script is missing")
    spec = spec_from_file_location("v52_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name.endswith("evidence_bound_successor_v52.toml")
    assert args.stress.name == "v52_growth_sizing_stress_20260816_v1.json"
    assert args.preflight == Path("flat.json")
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def test_v52_publication_binds_all_behavior_changing_generators() -> None:
    """Immutable acceptance must detect relevant source drift."""
    spec = spec_from_file_location("v52_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    names = {path.name for path in module._SPEC.generator_files}

    assert "v52_poststart_acceptance.py" in names
    assert "hype_compression_alignment_provider.py" in names
    assert "hype_breakout_compression_provider.py" in names
    assert "cohort_maximum_hold_policy.py" in names
