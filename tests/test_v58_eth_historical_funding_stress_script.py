"""CLI boundary for immutable V58 ETH historical funding stress."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts/v58_eth_historical_funding_stress.py"


def test_publishes_one_immutable_authority_none_report(tmp_path: Path) -> None:
    """The command exposes no live or sizing authority and cannot overwrite."""
    module = _module()
    inputs = [tmp_path / name for name in ("funding", "manifest", "stress", "current")]
    for path in inputs:
        path.write_text("{}", encoding="utf-8")
    output = tmp_path / "report.json"
    expected = {
        "mode": "v58_eth_historical_funding_stress_v1",
        "execution_authority": "none",
        "sizing_input": False,
        "live_change_supported": False,
    }
    module.load_v58_eth_historical_funding_stress = lambda **_: expected
    args = module.build_parser().parse_args(
        [
            "--funding",
            str(inputs[0]),
            "--manifest",
            str(inputs[1]),
            "--stress",
            str(inputs[2]),
            "--current-context",
            str(inputs[3]),
            "--out",
            str(output),
        ]
    )

    observed = module.publish_report(args)

    assert observed == expected
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(args)


def _module() -> ModuleType:
    spec = spec_from_file_location("v58_eth_historical_funding_stress_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V58 ETH historical funding stress script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
