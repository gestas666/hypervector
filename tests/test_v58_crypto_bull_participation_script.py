"""Immutable command tests for the crypto bull-participation replay."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.crypto_bull_participation_experiment import (
    CryptoBullExperimentResult,
)
from hypervector.research.crypto_bull_participation_historical import (
    CryptoBullHistoricalInputs,
)


def test_command_is_report_only_and_publishes_immutable_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one-shot command cannot place orders and binds its result files."""
    module = _load_module()
    prereg = tmp_path / "prereg.json"
    prereg.write_text(
        json.dumps(
            {
                "schema_version": "v58_crypto_bull_breadth_participation_preregistration_v1",
                "hypothesis_id": "V58_CRYPTO_BULL_BREADTH_PARTICIPATION_LONG_V1",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "result"
    args = module.build_parser().parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--preregistration",
            str(prereg),
            "--output",
            str(output),
        ]
    )
    empty_inputs = CryptoBullHistoricalInputs({}, {}, {}, ())
    result = CryptoBullExperimentResult(
        report={"authority": {"execution_authority": "none"}},
        trade_rows=(),
    )
    monkeypatch.setattr(module, "_source_evidence", lambda *_args: {"source": {}})
    monkeypatch.setattr(module, "_generator_identity", lambda *_args: {"sha256": "a"})
    monkeypatch.setattr(
        module, "load_crypto_bull_historical_inputs", lambda *_args: empty_inputs
    )
    monkeypatch.setattr(
        module, "run_crypto_bull_participation_historical", lambda *_args: result
    )
    monkeypatch.setattr(module, "_require_unchanged", lambda *_args: None)

    published = module.run_command(args)

    assert published == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report["authority"]["execution_authority"] == "none"
    assert report["input_evidence"] == {"source": {}}
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert pd.read_parquet(output / "trades.parquet").empty
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def _load_module() -> ModuleType:
    path = Path("scripts/v58_crypto_bull_participation.py")
    spec = importlib.util.spec_from_file_location("v58_crypto_bull_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
