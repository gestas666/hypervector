from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.btc_negative_funding_breakout_historical import (
    BtcNegativeFundingBreakoutPartition,
)

from btc_negative_funding_breakout_fixtures import (
    partitioned_negative_funding_breakout_bars,
)


def test_command_publishes_source_bound_authority_none_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind the immutable result to its preregistration, inputs, and generators."""
    module = _load_module()
    bars_path, funding_path = _write_inputs(tmp_path)
    preregistration = _write_preregistration(tmp_path, bars_path, funding_path)
    bars = pd.read_parquet(bars_path)
    start = pd.Timestamp(bars["timestamp"].min())
    partitions = tuple(
        BtcNegativeFundingBreakoutPartition(
            name,
            start + pd.Timedelta(hours=63 * offset),
            start + pd.Timedelta(hours=63 * (offset + 1)),
        )
        for offset, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    monkeypatch.setattr(
        module,
        "frozen_btc_negative_funding_breakout_partitions",
        lambda: partitions,
    )
    output = tmp_path / "immutable_result"
    args = module.build_parser().parse_args(
        [
            "--bars",
            str(bars_path),
            "--funding",
            str(funding_path),
            "--preregistration",
            str(preregistration),
            "--output",
            str(output),
        ]
    )
    published = module.run_command(args)
    assert published == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report["hypothesis_id"] == (
        "V58_BTC_NEGATIVE_FUNDING_HOURLY_BREAKOUT_LONG_V1"
    )
    assert report["authority"]["execution_authority"] == "none"
    assert len(report["summary_rows"]) == 27
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert report["generator_identity"]["aggregate_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    bars, funding = partitioned_negative_funding_breakout_bars()
    bars_path = tmp_path / "bars.parquet"
    bars.reset_index(names="timestamp").to_parquet(bars_path, index=False)
    funding_path = tmp_path / "funding.parquet"
    pd.DataFrame(
        {
            "timestamp": funding.index,
            "funding_rate": funding.to_numpy(),
            "source": "hl_funding_history",
        }
    ).to_parquet(funding_path, index=False)
    return bars_path, funding_path


def _write_preregistration(
    tmp_path: Path,
    bars_path: Path,
    funding_path: Path,
) -> Path:
    path = tmp_path / "preregistration.json"
    payload = {
        "schema_version": (
            "v58_btc_negative_funding_hourly_breakout_preregistration_v1"
        ),
        "hypothesis_id": "V58_BTC_NEGATIVE_FUNDING_HOURLY_BREAKOUT_LONG_V1",
        "authority": {"execution_authority": "none"},
        "source_evidence": {
            "bars": {"path": str(bars_path.resolve()), **file_evidence(bars_path)},
            "funding": {
                "path": str(funding_path.resolve()),
                **file_evidence(funding_path),
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_negative_funding_hourly_breakout.py")
    spec = importlib.util.spec_from_file_location("btc_negative_funding_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
