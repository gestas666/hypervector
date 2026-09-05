"""Tests for the immutable v52 common-window portfolio command."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v52_common_window_portfolio.py")


def _module() -> object:
    """Load the standalone script without spawning a subprocess."""
    spec = importlib.util.spec_from_file_location("v52_common_window_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v52 common-window script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_loads_exact_sources_and_reconciles_real_economics(
    tmp_path: Path,
) -> None:
    """The production sources must yield three route-native common-window trades."""
    module = _module()
    args = module.build_parser().parse_args(["--out", str(tmp_path / "report.json")])

    report = module.run(args)

    full = report["windows"]["opened_common"]["nominal"]["v52_full"]
    assert full["completed_trades"] == 3
    assert full["net_pnl_usd"] == pytest.approx(109.1747772705)
    assert report["profile"]["profile_id"].endswith("successor_v52")
    assert report["profile"]["configured_assets"] == ["BTC", "HYPE"]
    assert len(report["data_evidence"]) == 5
    assert report["sidecar_contract"]["cohort"] == "aligned_only"
    assert report["decision"] == "collect_forward_v52_no_live_change_from_this_report"


def test_command_publishes_once_and_refuses_overwrite(tmp_path: Path) -> None:
    """An immutable evidence identity cannot be replaced by a later run."""
    module = _module()
    out = tmp_path / "report.json"
    args = module.build_parser().parse_args(["--out", str(out)])
    report = module.run(args)

    module.publish(out, report)
    with pytest.raises(FileExistsError):
        module.publish(out, report)
