"""CLI contract for immutable v55 post-start technical acceptance."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path("scripts/v55_poststart_acceptance.py")


def test_v55_parser_binds_exact_config_and_requires_evidence() -> None:
    """The publisher cannot default to a prior profile or missing preflight."""
    spec = spec_from_file_location("v55_poststart_acceptance_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.build_parser().parse_args(
        ["--candidate", "candidate.json", "--preflight", "flat.json"]
    )

    assert args.config.name == "multi_asset_growth_first_5000_spcx_cash_open_v55.toml"
    assert args.candidate == Path("candidate.json")
    assert args.preflight == Path("flat.json")
