"""CLI contract for immutable v57 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path("scripts/v57_poststart_acceptance.py")


def test_v57_parser_binds_exact_config_and_requires_preflight() -> None:
    """The publisher cannot default to v56 or omit transition evidence."""
    assert _SCRIPT.is_file(), "v57 post-start publisher is missing"
    spec = spec_from_file_location("v57_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(["--preflight", "flat.json"])

    assert args.config.name == (
        "multi_asset_growth_first_5000_spcx_short_containment_v57.toml"
    )
    assert args.preflight == Path("flat.json")
