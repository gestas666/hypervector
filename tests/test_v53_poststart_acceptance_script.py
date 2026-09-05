"""CLI contract for immutable v53 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path("scripts/v53_poststart_acceptance.py")


def test_v53_parser_binds_exact_config_and_requires_preflight() -> None:
    """The publisher cannot default to an old profile or stale preflight."""
    spec = spec_from_file_location("v53_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name == (
        "multi_asset_growth_first_5000_hype_freshness_repair_v53.toml"
    )
    assert args.stress.name == "v53_growth_sizing_stress_20260817_v1.json"
    assert args.preflight == Path("flat.json")
