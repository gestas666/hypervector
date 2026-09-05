"""Streaming publication tests for the V58 BRENTOIL opposite-exit audit."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts/v58_brentoil_opposite_exit_audit.py"
_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def test_streaming_reader_freezes_only_complete_matching_rows(tmp_path: Path) -> None:
    """The large append-only ledger must be filtered without consuming a partial tail."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    matching = _row(_STRATEGY)
    unrelated = _row("unrelated")
    complete = _jsonl(matching) + _jsonl(unrelated)
    ledger.write_bytes(complete + b'{"partial":')

    rows, evidence = module._read_matching_routing_prefix(ledger)

    assert rows == (matching,)
    assert evidence["bytes"] == len(complete)
    assert evidence["rows"] == 2
    assert evidence["matching_rows"] == 1
    ledger.write_bytes(b"x" + ledger.read_bytes()[1:])
    with pytest.raises(ValueError, match="changed during evaluation"):
        module._require_prefix_unchanged(ledger, evidence)


def test_publisher_is_immutable_and_authority_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI must publish once and cannot gain execution authority."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"fixture":true}\n', encoding="utf-8")
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(_jsonl(_row(_STRATEGY)))
    output = tmp_path / "report.json"
    expected = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
            "runtime_strategy_changed": False,
        }
    }
    monkeypatch.setattr(
        module, "build_v58_brentoil_opposite_exit_audit", lambda *_: expected
    )
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--decision-ledger",
            str(ledger),
            "--out",
            str(output),
        ]
    )

    report = module.publish_report(args)

    assert report["contract"]["execution_authority"] == "none"
    assert json.loads(output.read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(args)


def _row(strategy_id: str) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "run_id": "bidirectional-live-1787166474078",
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": (
            "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
        ),
        "payload": {
            "evaluations": [
                {
                    "strategy_id": strategy_id,
                    "symbol": "xyz:BRENTOIL",
                    "decision_time_ms": 1,
                    "eligible": False,
                }
            ],
            "actions": [],
            "withheld": [],
        },
    }


def _jsonl(row: dict[str, object]) -> bytes:
    return json.dumps(row, separators=(",", ":")).encode() + b"\n"


def _module() -> ModuleType:
    spec = spec_from_file_location("v58_brentoil_opposite_exit_audit_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V58 BRENTOIL opposite-exit audit script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
