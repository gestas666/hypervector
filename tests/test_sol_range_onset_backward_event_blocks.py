"""Tests for immutable gap-safe SOL backward event blocks."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.sol_range_onset_backward_challenge import PreparedGapBlock
from hypervector.research.sol_range_onset_backward_event_blocks import (
    prepare_backward_event_blocks,
    store_backward_event_blocks,
)

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "sol_range_onset_backward_event_blocks.py"
)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_backward_event_blocks", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _block(number: int, start: str, minutes: int) -> PreparedGapBlock:
    index = pd.date_range(start, periods=minutes, freq="1min")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
            "source": "hl",
        },
        index=index,
    )
    return PreparedGapBlock(
        number,
        index[0],
        index[-1] + pd.Timedelta(minutes=1),
        minutes,
        0,
        bars,
    )


def test_prepare_aligns_to_funding_hour_with_complete_cadence() -> None:
    sufficient = _block(1, "2025-03-22T10:50:00Z", 1_821)
    insufficient = _block(2, "2025-03-25T10:10:00Z", 60)

    prepared = prepare_backward_event_blocks(
        (sufficient, insufficient),
        warmup_hours=30,
    )

    first = prepared[0]
    assert first.signal_start == pd.Timestamp("2025-03-22T11:00:00Z")
    assert first.execution_start == pd.Timestamp("2025-03-23T17:00:00Z")
    assert first.status == "complete"
    assert first.execution_rows == 11
    assert first.bars.index[0] == first.signal_start
    assert first.bars.index[-1] == sufficient.end - pd.Timedelta(minutes=1)
    assert prepared[1].status == "insufficient_warmup"


def test_store_publishes_checksum_manifest_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    prepared = prepare_backward_event_blocks(
        (_block(1, "2025-03-01T00:00:00Z", 1_802),),
        warmup_hours=30,
    )
    output = tmp_path / "blocks"

    stored = store_backward_event_blocks(
        output,
        prepared,
        source_evidence={"bars_sha256": "abc", "funding_sha256": "def"},
    )

    manifest = json.loads(stored.read_text(encoding="utf-8"))
    assert manifest["execution_authority"] == "none"
    assert manifest["blocks"][0]["status"] == "complete"
    assert manifest["blocks"][0]["files"]["bars.parquet"]["sha256"]
    assert (output / "block-01" / "bars.parquet").is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        store_backward_event_blocks(
            output,
            prepared,
            source_evidence={"bars_sha256": "abc", "funding_sha256": "def"},
        )


def test_backward_event_block_script_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    bars_path = tmp_path / "bars" / "candles.parquet"
    funding_path = tmp_path / "funding" / "funding.parquet"
    bars_path.parent.mkdir()
    funding_path.parent.mkdir()
    bars_path.write_bytes(b"bars")
    funding_path.write_bytes(b"funding")
    (bars_path.parent / "manifest.json").write_text("{}", encoding="utf-8")
    (funding_path.parent / "manifest.json").write_text("{}", encoding="utf-8")
    source = _block(1, "2025-03-01T00:00:00Z", 1_802)
    monkeypatch.setattr(
        module,
        "load_verified_sol_backward_inputs",
        lambda **_: (pd.DataFrame(), pd.Series(dtype=float)),
    )
    monkeypatch.setattr(
        module, "prepare_gap_safe_blocks", lambda *_args, **_kwargs: (source,)
    )
    output = tmp_path / "output"
    arguments = [
        "--bars",
        str(bars_path),
        "--funding",
        str(funding_path),
        "--start",
        "2025-03-01T00:00:00Z",
        "--end",
        "2025-03-03T00:00:00Z",
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    assert json.loads((output / "manifest.json").read_text())["block_count"] == 1
    assert module.main(arguments) == 1
