"""Immutable BTC trend-pullback failure attribution command tests."""

from __future__ import annotations

import pytest

import importlib.util
import json
from pathlib import Path

import pandas as pd


_SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "v58_btc_trend_pullback_failure_attribution.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "v58_btc_trend_pullback_failure_attribution_script", _SCRIPT
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("BTC trend-pullback failure attribution script is unavailable")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.mark.evidence
def test_command_publishes_source_bound_report_only_bundle(tmp_path: Path) -> None:
    """The fixed command publishes all 147 observations without authority."""
    output = tmp_path / "attribution"
    args = _MODULE.build_parser().parse_args(["--output", str(output)])

    observed = _MODULE.run_command(args)

    assert observed == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["diagnostic_id"] == "V58_BTC_TREND_PULLBACK_FAILURE_ATTRIBUTION_V1"
    assert report["observation_rows"] == 147
    assert report["authority"]["execution_authority"] == "none"
    assert report["diagnosis"]["candidate_remains_rejected"] is True
    rows = pd.read_parquet(output / "observations.parquet")
    assert len(rows) == 147
    assert set(rows["partition"]) == {
        "development",
        "validation",
        "pseudo_holdout",
    }
    assert set(rows["outcome"]) == {"stop", "target"}
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"report.json", "observations.parquet"}
