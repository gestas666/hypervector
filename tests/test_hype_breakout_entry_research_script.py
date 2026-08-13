"""CLI contract tests for immutable HYPE entry research evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_breakout_entry_research.py"


def _load() -> object:
    spec = spec_from_file_location("hype_breakout_entry_research_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE entry research script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_derives_exact_feature_and_trade_sidecars() -> None:
    """The summary hash-links both signal features and lifecycle evidence."""
    module = _load()
    args = module.build_parser().parse_args(["--out", "result.json"])

    summary, features, trades = module.output_paths(args.out)

    assert summary == Path("result.json")
    assert features == Path("result.features.parquet")
    assert trades == Path("result.trades.parquet")
