"""HIP-3 symbol identity at report-only funding research boundaries."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def test_one_blocker_runner_preserves_hip3_namespace() -> None:
    """The single-hypothesis runner must retain the lowercase dex name."""
    module = _module(
        "cohort_one_blocker_execution_feasibility_script",
        "scripts/cohort_one_blocker_execution_feasibility.py",
    )

    normalized = module._normalized_symbol("xyz:SPCX")  # type: ignore[attr-defined]

    assert normalized == "xyz:SPCX"


def test_opportunity_matrix_funding_paths_preserve_hip3_namespace() -> None:
    """Funding-path keys must match exact configured HIP-3 symbols."""
    module = _module(
        "cohort_execution_opportunity_matrix_script",
        "scripts/cohort_execution_opportunity_matrix.py",
    )

    paths = module._funding_paths(  # type: ignore[attr-defined]
        ["xyz:SPCX=/tmp/spcx-funding.parquet"]
    )

    assert paths == {"xyz:SPCX": Path("/tmp/spcx-funding.parquet")}


def _module(name: str, path: str) -> ModuleType:
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script module: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
