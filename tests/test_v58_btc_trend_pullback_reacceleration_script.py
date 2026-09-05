from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path("scripts/v58_btc_trend_pullback_reacceleration.py")


def test_parser_retains_registered_identity_and_explicit_output() -> None:
    """Bind the immutable command to the registered source contract."""
    specification = importlib.util.spec_from_file_location(
        "btc_pullback_script", _SCRIPT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    args = module.build_parser().parse_args(["--output", "evidence/new"])
    assert args.output == Path("evidence/new")
    assert "v58-btc-trend-pullback-reacceleration-preregistration" in str(
        args.preregistration
    )
    assert args.backtest_lab_root == Path("../backtest-lab/backtest_lab")
    assert {
        "src/hypervector/research/btc_trend_pullback_route_competition.py",
        "src/hypervector/research/btc_v58_hulk_route_source.py",
        "src/hypervector/research/btc_sweep_primary_relaxation.py",
        "src/hypervector/research/btc_sweep_primary_relaxation_replay.py",
    } <= set(module._GENERATORS)
