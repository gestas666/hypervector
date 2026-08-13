"""CLI tests for immutable v42 successor-design evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/v42_successor_design.py")


def test_report_is_source_bound_and_execution_incapable(tmp_path: Path) -> None:
    """The command captures every input without granting runtime authority."""
    module = _module()
    args = module.build_parser().parse_args(["--out", str(tmp_path / "report.json")])

    report = module.run_report(args)

    assert report["contract"]["execution_authority"] == "none"
    assert report["candidate"]["profile_id"].endswith("v42")
    assert set(report["evidence"]) == {
        "config",
        "v41_readiness",
        "current_checkpoint",
        "hype_exit_evidence",
    }
    assert report["generator_identity"]["files"]
    module.require_unchanged_inputs(report)


def _module() -> ModuleType:
    spec = spec_from_file_location("v42_successor_design_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v42 successor-design script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
