"""CLI boundary for immutable V58 ETH duration checkpoint evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts/v58_eth_duration_checkpoint.py"


def test_publishes_one_immutable_authority_none_report(tmp_path: Path) -> None:
    """The command writes only the exact report returned by the loader."""
    module = _module()
    status = tmp_path / "status.json"
    status.write_text("{}")
    output = tmp_path / "report.json"
    expected = {
        "mode": "v58_eth_fixed_entry_duration_checkpoint_v1",
        "execution_authority": "none",
    }
    module.load_v58_eth_duration_checkpoint_report = lambda path: expected
    args = module.build_parser().parse_args(
        ["--status", str(status), "--out", str(output)]
    )

    observed = module.publish_report(args)

    assert observed == expected
    assert json.loads(output.read_text()) == expected


def _module() -> ModuleType:
    spec = spec_from_file_location("v58_eth_duration_checkpoint_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V58 ETH duration checkpoint script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
