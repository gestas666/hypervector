"""Operator contract for the report-only source event-frequency audit."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


_SCRIPT = Path("scripts/hypervelocity_source_event_frequency.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("source_event_frequency", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load event-frequency script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_requires_explicit_pinned_evidence_and_output() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--profile",
            "profile.toml",
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--candles",
            "candles.parquet",
            "--out",
            "frequency.json",
        ]
    )

    assert args.profile == Path("profile.toml")
    assert args.labels == Path("labels.parquet")
    assert args.labels_metadata == Path("labels.json")
    assert args.candles == [Path("candles.parquet")]
    assert args.out == Path("frequency.json")
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "create_armed" not in source
    assert "private_key" not in source
    assert "submit_entry" not in source


def test_candle_provenance_rejects_non_hyperliquid_rows(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "candles.parquet"
    pd.DataFrame({"source": ["hl", "binance"]}).to_parquet(path)

    with pytest.raises(ValueError, match="non-Hyperliquid"):
        module._candle_source_counts([path])


def test_candle_provenance_retains_gap_fill_counts(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "candles.parquet"
    pd.DataFrame({"source": ["hl", "hl_gap_fill", "hl"]}).to_parquet(path)

    assert module._candle_source_counts([path]) == {"hl": 2, "hl_gap_fill": 1}
