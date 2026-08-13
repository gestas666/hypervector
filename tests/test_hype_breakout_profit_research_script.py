"""CLI contract tests for immutable HYPE profit research evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_breakout_profit_research.py"


def _load() -> object:
    spec = spec_from_file_location("hype_breakout_profit_research_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE profit research script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_derives_a_separate_immutable_trade_sidecar() -> None:
    """The summary cannot replace or hide exact lifecycle evidence."""
    module = _load()
    args = module.build_parser().parse_args(["--out", "result.json"])

    summary, trades = module.output_paths(args.out)

    assert summary == Path("result.json")
    assert trades == Path("result.trades.parquet")
