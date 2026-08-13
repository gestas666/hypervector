"""Immutable command contract for the HIP-3 entry-timing challenger."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from hypervector.live.hip3_cohort_providers import HIP3_SWING_INDEX_STRATEGY

_SCRIPT = Path("scripts/hip3_entry_timing_challenger.py")
_SPEC = importlib.util.spec_from_file_location("hip3_entry_timing_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_command_publishes_report_only_immutable_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "timing.json"
    trades = tmp_path / "timing.parquet"

    def fake_case(
        strategy_id: str, source: Path
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        assert strategy_id == HIP3_SWING_INDEX_STRATEGY
        assert source == Path("source.json")
        return (
            {
                "strategy_id": strategy_id,
                "execution_authority": "none",
                "automatic_promotion": False,
                "runtime_strategy_changed": False,
            },
            [],
        )

    monkeypatch.setattr(_MODULE, "_run_case", fake_case)
    args = _MODULE.build_parser().parse_args(
        [
            "--case",
            f"{HIP3_SWING_INDEX_STRATEGY}=source.json",
            "--output",
            str(output),
            "--trades-output",
            str(trades),
        ]
    )

    report = _MODULE.run_command(args)

    assert output.is_file() and trades.is_file()
    assert report["schema_version"] == "hip3_entry_timing_challenger_v1"
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["runtime_strategy_changed"] is False
    assert report["trade_sidecar"]["rows"] == 0
