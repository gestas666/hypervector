"""CLI contracts for immutable v30 forward-readiness deltas."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

from test_v30_forward_delta import _report, _routes


SCRIPT = Path("scripts/v30_live_forward_delta.py")


def _script() -> ModuleType:
    spec = spec_from_file_location("v30_live_forward_delta_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_publishes_source_bound_immutable_delta(tmp_path: Path) -> None:
    """The operator command must bind both reports and refuse overwrite."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "delta.json"
    before.write_text(
        json.dumps(_report(timestamp="2026-08-09T17:00:00Z", routes=_routes()))
    )
    after_routes = _routes()
    for route in after_routes:
        route["forward_evaluations"] = 110
    after.write_text(
        json.dumps(_report(timestamp="2026-08-09T17:10:00Z", routes=after_routes))
    )
    module = _script()

    assert (
        module.main(
            [
                "--before",
                str(before),
                "--after",
                str(after),
                "--out",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(output.read_text())
    assert result["source_evidence"]["before"]["sha256"]
    assert result["source_evidence"]["after"]["sha256"]
    assert (
        module.main(
            ["--before", str(before), "--after", str(after), "--out", str(output)]
        )
        == 2
    )
