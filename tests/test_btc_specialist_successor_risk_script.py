"""CLI contract for immutable BTC successor risk evidence."""

import pytest

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

from types import ModuleType

_SCRIPT = Path("scripts/btc_specialist_successor_risk.py")


@pytest.mark.evidence
def test_command_writes_report_only_current_and_growth_scenarios(
    tmp_path: Path,
) -> None:
    """The CLI publishes once without an execution-authority surface."""
    module = _load_module()
    output = tmp_path / "risk.json"
    args = module.build_parser().parse_args(["--output", str(output)])

    result = module.run(args)

    assert result == 0
    report = json.loads(output.read_text())
    assert report["execution_authority"] == "none"
    assert [row["account_value_usd"] for row in report["scenarios"]] == [
        500.0,
        5_000.0,
    ]
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def _load_module() -> ModuleType:
    spec = spec_from_file_location("btc_specialist_successor_risk_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
