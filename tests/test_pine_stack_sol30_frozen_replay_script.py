"""Command-contract tests for the frozen SOL 30-minute Pine replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path("scripts/pine_stack_sol30_frozen_replay.py")


def _module():
    spec = importlib.util.spec_from_file_location(
        "pine_stack_sol30_frozen_replay", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import SOL Pine replay script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_report_only_sol30_output_contract() -> None:
    """The command must expose no symbol, route, or parameter search arguments."""
    module = _module()
    args = module.build_parser().parse_args([])

    assert args.output == Path(
        "data/logs/research/pine_stack_sol30_frozen_later_windows_v1.json"
    )
    assert args.data_root == Path("data")
    assert not hasattr(args, "symbol")
    assert not hasattr(args, "candidate")
    assert not hasattr(args, "exit_variant")


def test_partition_names_are_validation_then_pseudo_holdout() -> None:
    """The replay must not reopen development or conditionally skip holdout."""
    module = _module()

    assert module._PARTITIONS == ("validation", "pseudo_holdout")
    assert module._ROUTE.symbol == "SOL"
    assert module._ROUTE.bar_minutes == 30
    assert module._ROUTE.candidate == "cs_trend"
    assert module._ROUTE.exit_variant == "cs_flip"
