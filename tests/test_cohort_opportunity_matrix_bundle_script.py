"""CLI tests for the report-only opportunity-matrix display bundle."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_opportunity_matrix_bundle.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("cohort_opportunity_matrix_bundle_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_once_publishes_exact_report_only_inputs(tmp_path: Path) -> None:
    """The CLI forwards only local evidence paths to the atomic publisher."""
    module = _load_module()
    calls: list[tuple[Path, tuple[Path, ...], Path]] = []

    def publish(
        primary: Path,
        supplemental: tuple[Path, ...],
        output: Path,
    ) -> dict[str, object]:
        calls.append((primary, supplemental, output))
        return {"supplemental_forward_challengers": [{}, {}]}

    args = module.build_parser().parse_args(
        [
            "--primary",
            "primary.json",
            "--supplemental",
            "hype.json",
            "--supplemental",
            "sol.json",
            "--out",
            str(tmp_path / "latest.json"),
            "--once",
        ]
    )

    assert module.run_bundle_loop(args, publish_fn=publish) == 0
    assert calls == [
        (
            Path("primary.json"),
            (Path("hype.json"), Path("sol.json")),
            tmp_path / "latest.json",
        )
    ]
    source = SCRIPT.read_text(encoding="utf-8")
    assert "execution_authority" in source
    assert "submit" not in source
    assert "private_key" not in source


def test_once_discloses_invalid_input_without_success(tmp_path: Path) -> None:
    """An invalid observer produces a nonzero result rather than stale success."""
    module = _load_module()

    def publish(
        _primary: Path,
        _supplemental: tuple[Path, ...],
        _output: Path,
    ) -> dict[str, object]:
        raise ValueError("observer contract invalid")

    args = module.build_parser().parse_args(
        [
            "--primary",
            "primary.json",
            "--supplemental",
            "hype.json",
            "--out",
            str(tmp_path / "latest.json"),
            "--once",
        ]
    )

    assert module.run_bundle_loop(args, publish_fn=publish) == 2


def test_destination_lock_rejects_a_second_writer(tmp_path: Path) -> None:
    """Only one process may publish a given rolling display artifact."""
    module = _load_module()
    destination = tmp_path / "latest.json"

    with module.destination_lock(destination):
        with pytest.raises(RuntimeError, match="already has an active writer"):
            with module.destination_lock(destination):
                pytest.fail("a second writer acquired the destination lock")
