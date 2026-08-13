"""CLI contract tests for immutable HYPE L2 entry features."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "hype_entry_l2_feature_materialization.py"
)


def _load() -> object:
    spec = spec_from_file_location("hype_entry_l2_materialization_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE L2 feature script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_inputs_and_hash_linked_outputs() -> None:
    """The command binds source features, coverage audit, and sidecars."""
    module = _load()
    args = module.build_parser().parse_args(["--out", "result.json"])

    summary, features, coverage = module.output_paths(args.out)

    assert "development" in args.features.name
    assert args.audit_index.name == "index.parquet"
    assert args.sampling_interval_ms is None
    assert summary == Path("result.json")
    assert features == Path("result.features.parquet")
    assert coverage == Path("result.coverage.parquet")


def test_output_requires_json_suffix() -> None:
    """Immutable report names cannot silently diverge from their sidecars."""
    module = _load()

    try:
        module.output_paths(Path("result.txt"))
    except ValueError as exc:
        assert "must use .json" in str(exc)
    else:
        raise AssertionError("non-JSON materialization output was accepted")
