"""CLI contract tests for predeclared HYPE L2 model research."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_entry_l2_model_research.py"


def _load() -> object:
    spec = spec_from_file_location("hype_entry_l2_model_research_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE L2 model script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_binds_predeclared_plan_and_immutable_sidecars() -> None:
    """No model knobs are exposed after the candidate plan is frozen."""
    module = _load()
    args = module.build_parser().parse_args(["--out", "result.json"])

    summary, folds, predictions = module.output_paths(args.out)

    assert "model_plan" in args.plan.name
    assert "development" in args.features.name
    assert summary == Path("result.json")
    assert folds == Path("result.folds.parquet")
    assert predictions == Path("result.predictions.parquet")
    assert not hasattr(args, "fold_count")
    assert not hasattr(args, "modeled_round_trip_bps")


def test_output_requires_json_suffix() -> None:
    """Summary and OOS sidecars retain one deterministic naming contract."""
    module = _load()

    with pytest.raises(ValueError, match="must use .json"):
        module.output_paths(Path("result.txt"))
