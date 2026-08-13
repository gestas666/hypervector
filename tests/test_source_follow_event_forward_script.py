"""CLI contract for immutable live source-event forward evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_event_forward_audit.py")
    spec = importlib.util.spec_from_file_location("source_event_forward_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quiet_live_run_publishes_zero_event_evidence(tmp_path: Path) -> None:
    """No-event windows must remain publishable and explicitly non-executable."""
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text("\n".join(json.dumps(row) for row in _quiet_rows()) + "\n")
    database = tmp_path / "unused.duckdb"
    database.write_bytes(b"quiet-event-audit-does-not-query")
    output = tmp_path / "audit.json"

    result = _script().main(
        [
            "--config",
            "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_canary.toml",
            "--decisions",
            str(decisions),
            "--database",
            str(database),
            "--run-id",
            "quiet-run",
            "--out",
            str(output),
        ]
    )

    assert result == 0
    report = json.loads(output.read_text())
    assert report["event_rows"] == 0
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["minimum_range_bps"] == 12.0
    assert report["target_bps"] == 26.666666666666664
    assert report["measurement_contract_matches_current_config"] is True
    assert report["profile_fingerprint_match"] is False


def _quiet_rows() -> list[dict[str, object]]:
    return [
        {
            "sequence": 0,
            "run_id": "quiet-run",
            "event_type": "configuration_identity",
            "profile_id": "hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1",
            "profile_fingerprint": "old-process-fingerprint",
            "payload": {
                "symbol": "BTC",
                "regime_policy": {
                    "minimum_completed_5m_range_bps": 12.0,
                    "maximum_completed_5m_range_bps": 100.0,
                },
                "exits": {"target_price_fraction": 0.0026666666666666666},
            },
        },
        {
            "sequence": 1,
            "run_id": "quiet-run",
            "event_type": "regime_decision",
            "payload": {"source_event": False},
        },
    ]
