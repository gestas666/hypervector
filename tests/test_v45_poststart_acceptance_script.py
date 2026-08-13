"""Publication boundary for immutable v45 technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v45_poststart_acceptance.py")


def test_v45_parser_binds_growth_risk_friction_and_required_preflight() -> None:
    """The report command has no execution surface and names exact v45 inputs."""
    script = _module()
    parser = script.build_parser()
    args = parser.parse_args(["--preflight", "flat.json"])

    assert args.config.name.endswith("growth_sizing_candidate_v45.toml")
    assert args.risk.name == "v45_btc_specialist_successor_risk_20260812_v1.json"
    assert args.friction.name == "v45_growth_sizing_stress_20260812_v2.json"
    assert args.preflight == Path("flat.json")
    help_text = parser.format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v45 post-start acceptance script is missing")
    spec = spec_from_file_location("v45_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v45 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
