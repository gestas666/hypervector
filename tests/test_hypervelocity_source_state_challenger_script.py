"""Command contract for the source-state development challenger."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_state_challenger.py")
    spec = importlib.util.spec_from_file_location("source_state_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source state script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_requires_causal_source_labels_and_multiple_replays() -> None:
    """The development command binds exact source labels and replay populations."""
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
            "--strict-labels",
            "labels.parquet",
            "--expected-resolved",
            "259",
            "--expected-liquidations",
            "48",
            "--out",
            "report.json",
            "--model-dir",
            "models",
        ]
    )

    assert args.replay == [Path("first.json"), Path("second.json")]
    assert args.strict_labels == Path("labels.parquet")
    assert args.n_splits == 5
