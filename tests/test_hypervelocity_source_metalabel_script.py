"""Command contract for corrected strict-source metalabel reports."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_metalabel.py")
    spec = importlib.util.spec_from_file_location("source_metalabel_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source metalabel script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_collects_multiple_replay_blocks_and_defaults_to_five_folds() -> None:
    """Disconnected blocks are explicit inputs to one five-fold experiment."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--replay",
            "first.json",
            "--replay",
            "second.json",
            "--bars",
            "bars.parquet",
            "--config",
            "config.toml",
            "--expected-resolved",
            "213",
            "--expected-liquidations",
            "39",
            "--out",
            "report.json",
            "--model-dir",
            "models",
        ]
    )

    assert args.replay == [Path("first.json"), Path("second.json")]
    assert args.n_splits == 5
    assert args.expected_resolved == 213
    assert args.expected_liquidations == 39
