"""HIP-3 signal-source sensitivity script contract tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace

import pandas as pd


def test_parser_supplies_venue_path_data_root() -> None:
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "xyz:SKHX",
            "--database",
            "archive.duckdb",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-06-08T08:00:00Z",
            "--end",
            "2026-08-11T14:00:00Z",
            "--qualification-report",
            "qualification.json",
            "--liquidity-report",
            "liquidity.json",
            "--archive-audit-report",
            "audit.json",
            "--development-report",
            "development.json",
            "--observed-at",
            "2026-08-12T07:15:00Z",
            "--output",
            "output.json",
        ]
    )

    assert args.data_root == Path("data")


def test_midpoint_loader_uses_audited_cross_timeframe_path(monkeypatch: object) -> None:
    module = _module()
    expected = object()

    def load(*_args: object) -> dict[str, object]:
        return {"5m": object(), "15m": expected}

    monkeypatch.setattr(module.development, "_load_midpoints", load)

    observed = module._load_midpoint(
        SimpleNamespace(),
        {},
        pd.Timestamp("2026-06-08T08:00:00Z"),
        pd.Timestamp("2026-08-11T14:00:00Z"),
    )

    assert observed is expected


def _module() -> ModuleType:
    path = Path("scripts/hip3_signal_source_sensitivity.py").resolve()
    scripts = str(path.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = spec_from_file_location("hip3_signal_source_sensitivity_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load source-sensitivity script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
