"""Standalone v51 index source-transport parity command tests."""

from __future__ import annotations

from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_index_source_transport_parity import (
    Hip3IndexSourceParityConfig,
)

_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_index_source_transport_parity.py"


def test_command_publishes_only_a_report_only_immutable_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The orchestration boundary must not acquire promotion or live authority."""
    module = _module()
    sources = module._LoadedSources(
        config=_config(),
        trades=pd.DataFrame(),
        archive_books=pd.DataFrame(),
        venue_candles=pd.DataFrame(),
        rest_rows=[],
        observer_rows=[],
        evidence={"audit": {"sha256": "a", "bytes": 1}},
        exact_files=(),
        prefixes=(),
    )
    report = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "scope": {"symbol": "xyz:SP500"},
        "coverage": {"observer_decisions": 8},
        "technical_assessment": {"source_transport_parity_resolved": True},
    }
    monkeypatch.setattr(module, "_load_sources", lambda _args: sources)
    monkeypatch.setattr(
        module, "build_hip3_index_source_transport_parity", lambda **_kwargs: report
    )
    monkeypatch.setattr(module, "_require_unchanged_sources", lambda _sources: None)
    output = tmp_path / "parity.json"

    published = module.run_command(_args(output))

    assert published["input_evidence"] == sources.evidence
    assert published["contract"]["execution_authority"] == "none"
    assert json.loads(output.read_text()) == published
    with pytest.raises(FileExistsError):
        module.run_command(_args(output))


def test_journal_route_contract_rejects_wrong_symbol() -> None:
    """A route cannot inherit another HIP-3 asset's frozen identity."""
    module = _module()
    journal = _journal()

    with pytest.raises(ValueError, match="requested route"):
        module._config_from_evidence(journal, _audit(), "xyz:SNDK")


def test_append_after_jsonl_prefix_does_not_rewrite_frozen_rows(tmp_path: Path) -> None:
    """Live appenders may grow while the exact consumed prefix stays immutable."""
    module = _module()
    path = tmp_path / "live.jsonl"
    path.write_text('{"sequence":1}\n')
    rows, evidence = module._read_jsonl_prefix(path, "live ledger")
    path.write_text(path.read_text() + '{"sequence":2}\n')

    module._require_prefix_unchanged(path, evidence)

    assert rows == [{"sequence": 1}]


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_index_source_transport_parity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(output: Path) -> Namespace:
    return Namespace(
        symbol="xyz:SP500",
        data_root=Path("data"),
        archive_audit=Path("audit.json"),
        journal=Path("journal.json"),
        observer=Path("observer.jsonl"),
        rest_ledger=Path("rest.jsonl"),
        output=output,
    )


def _config() -> Hip3IndexSourceParityConfig:
    return Hip3IndexSourceParityConfig(
        "xyz:SP500",
        "provider",
        "profile",
        1_800_000_000_000,
        1_800_000_900_000,
        Hip3BreakoutPressureConfig(4, 3, 5, 0.1, 120.0),
    )


def _audit() -> dict[str, object]:
    return {
        "symbol": "xyz:SP500",
        "market_family": "hip3",
        "requested_start_utc": "2026-08-12T06:45:00+00:00",
        "requested_end_utc": "2026-08-13T23:45:00+00:00",
        "chunk_seconds": 3600,
        "book_only": False,
        "complete": True,
    }


def _journal() -> dict[str, object]:
    return {
        "schema_version": "v51_index_source_parity_forward_v1",
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "routes": ["provider|xyz:SP500"],
        "frozen_signal_contract": {
            "provider_id": "provider",
            "profile_ids": {"xyz:SP500": "profile"},
            "timeframe": "15m",
            "breakout_lookback_bars": 32,
            "fast_ema": 21,
            "slow_ema": 55,
            "minimum_abs_imbalance": 0.1,
            "signal_maximum_stop_bps": 120.0,
        },
    }
