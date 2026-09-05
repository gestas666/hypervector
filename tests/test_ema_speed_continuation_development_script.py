"""Command and atomic-publication tests for EMA-speed development."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest


_SCRIPT = Path("scripts/ema_speed_continuation_development.py")


def test_command_is_report_only_and_has_no_live_flags(tmp_path: Path) -> None:
    """The frozen runner exposes evidence output but no execution controls."""
    parser = _module().build_parser()
    args = parser.parse_args(["--out-dir", str(tmp_path / "bundle")])
    assert args.database == Path("data/research/market.duckdb")
    assert args.out_dir == tmp_path / "bundle"
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source


def test_bundle_publication_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    """Report, trades, and manifest publish together under one immutable directory."""
    module = _module()
    out = tmp_path / "bundle"
    module.publish_bundle(
        out,
        {"execution_authority": "none", "report_only": True},
        pd.DataFrame({"trade_id": ["one"]}),
    )
    assert sorted(path.name for path in out.iterdir()) == [
        "manifest.json",
        "report.json",
        "trades.parquet",
    ]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_authority"] == "none"
    with pytest.raises(FileExistsError, match="bundle output exists"):
        module.publish_bundle(out, {}, pd.DataFrame())


def _module() -> ModuleType:
    spec = spec_from_file_location("ema_speed_continuation_development", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load EMA-speed script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
