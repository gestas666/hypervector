"""CLI tests for immutable execution-drag diagnostics."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/cohort_execution_drag_diagnostic.py")


def test_report_binds_checkpoint_and_publishes_once(tmp_path: Path) -> None:
    """A diagnostic must bind exact source bytes and never replace evidence."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "drag.json"
    raw = json.dumps({"audit": {"trade_reflections": {"trades": [_trade()]}}}).encode()
    checkpoint.write_bytes(raw)
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output)]
    )

    report = module.run_report(args)
    module.write_immutable_report(output, report)

    persisted = json.loads(output.read_text())
    assert persisted["evidence"]["checkpoint"]["sha256"] == sha256(raw).hexdigest()
    assert persisted["diagnostic"]["performance"]["total"][
        "execution_cash_drag_usd"
    ] == pytest.approx(0.021)
    with pytest.raises(FileExistsError, match="already exists"):
        module.write_immutable_report(output, report)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("execution-drag diagnostic script is missing")
    spec = spec_from_file_location("execution_drag_diagnostic_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load execution-drag diagnostic script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade() -> dict[str, object]:
    return {
        "strategy_id": "alpha",
        "symbol": "BTC",
        "side": "long",
        "net_pnl_usd": 1.0,
        "entry_margin_used_usd": 10.0,
        "net_return_on_margin_pct": 10.0,
        "fees_usd": 0.02,
        "funding_usd": -0.001,
    }
