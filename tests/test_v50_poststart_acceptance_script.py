"""Publication boundary for immutable v50 technical acceptance."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v50_poststart_acceptance.py")
_V51_SCRIPT = Path("scripts/v51_poststart_acceptance.py")


def test_v50_parser_binds_exact_evidence_and_requires_flat_preflight() -> None:
    """The report command must bind the six-asset v50 identity."""
    if not _SCRIPT.exists():
        pytest.fail("v50 post-start acceptance script is missing")
    spec = spec_from_file_location("v50_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert (
        args.config.name == "multi_asset_growth_first_5000_six_asset_candidate_v50.toml"
    )
    assert args.friction.name == "v50_growth_sizing_stress_20260813_v1.json"
    assert args.preflight == Path("flat.json")
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def test_v51_parser_binds_profit_protected_identity_and_flat_preflight() -> None:
    """The final report command cannot fall back to the unprotected v50 draft."""
    if not _V51_SCRIPT.exists():
        pytest.fail("v51 post-start acceptance script is missing")
    spec = spec_from_file_location("v51_poststart_acceptance_script", _V51_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name.endswith("six_asset_profit_lock_candidate_v51.toml")
    assert args.friction.name == "v51_growth_sizing_stress_20260813_v1.json"
    assert args.preflight == Path("flat.json")
    assert "--enabled" not in module.build_parser().format_help()
