"""Publication boundary for immutable v49 technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v49_poststart_acceptance.py")


def test_v49_parser_binds_exact_evidence_and_requires_flat_preflight() -> None:
    """The report-only command must bind the repaired v49 identity."""
    script = _module()
    args = script.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name == (
        "multi_asset_growth_first_5000_repaired_candidate_v49.toml"
    )
    assert args.friction.name == "v49_growth_sizing_stress_20260812_v1.json"
    assert args.preflight == Path("flat.json")
    help_text = script.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v49 post-start acceptance script is missing")
    spec = spec_from_file_location("v49_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v49 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
