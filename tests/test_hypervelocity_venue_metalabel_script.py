"""Command contract for observe-only Hypervelocity venue metalabel reports."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_venue_metalabel.py")
    spec = importlib.util.spec_from_file_location("venue_metalabel_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load venue metalabel script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_accepts_faithful_stop14_profile() -> None:
    """The target-before-stop label must be an explicit command identity."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--replay",
            "replay.json",
            "--bars",
            "bars.parquet",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--out",
            "report.json",
            "--model-dir",
            "models",
            "--candidate-profile",
            "faithful-stop14",
        ]
    )

    assert args.candidate_profile == "faithful-stop14"
