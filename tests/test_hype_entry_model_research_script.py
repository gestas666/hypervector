"""CLI contract tests for immutable HYPE entry-model evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_entry_model_research.py"


def _load() -> object:
    spec = spec_from_file_location("hype_entry_model_research_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE entry-model script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_development_input_and_exact_sidecars() -> None:
    """The command must hash-link folds and OOS predictions to one summary."""
    module = _load()
    args = module.build_parser().parse_args(["--out", "result.json"])

    summary, folds, predictions = module.output_paths(args.out)

    assert "development" in args.features.name
    assert args.fold_count == 5
    assert args.embargo_minutes == 60
    assert summary == Path("result.json")
    assert folds == Path("result.folds.parquet")
    assert predictions == Path("result.predictions.parquet")
