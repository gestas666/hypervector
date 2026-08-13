"""Command contract for immutable HT onset ranker evidence."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from test_ht_onset_metalabel import _market

SCRIPT = Path(__file__).parents[1] / "scripts" / "ht_onset_metalabel.py"


def test_command_publishes_authority_none_ranker_artifact(tmp_path: Path) -> None:
    """The command must freeze evidence without creating a runtime model."""
    module = _load_module()
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    bars.write_bytes(b"bars")
    funding.write_bytes(b"funding")
    output = tmp_path / "report.json"
    args = argparse.Namespace(
        symbol="BTC",
        bars=bars,
        funding=funding,
        holdout_days=5,
        out=output,
    )

    report = module.run_report(args, market_loader=_load_market)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["model_installed"] is False
    assert report["evidence"]["bars"]["sha256"]
    assert report["generator_identity"]["files"]


def _load_market(_bars: Path, _funding: Path) -> tuple[pd.DataFrame, object]:
    return _market(), {"fixture": "exact"}


def _load_module() -> ModuleType:
    spec = spec_from_file_location("ht_onset_metalabel_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
