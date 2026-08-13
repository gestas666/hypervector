"""Exact v39 HT side-authority artifact command tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "v39_ht_side_authority_challenger.py"
_RUN_ID = "bidirectional-live-1786453934555"


def test_command_publishes_exact_authority_none_decision_artifact(
    tmp_path: Path,
) -> None:
    module = _load_module()
    output = tmp_path / "side-authority.json"
    args = module.build_parser().parse_args(
        [
            "--database",
            str(tmp_path / "market.duckdb"),
            "--run-id",
            _RUN_ID,
            "--output",
            str(output),
        ]
    )

    report = module.run_command(args, row_loader=_rows)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["summary"]["eligible_onsets"] == 1
    assert report["summary"]["opposed_onsets"] == 1
    assert report["contract"]["execution_authority"] == "none"
    assert report["source"]["first_observed_at_utc"] == ("2026-08-11T13:00:00+00:00")
    assert set(report["generator_identity"]) == {
        "scripts/v39_ht_side_authority_challenger.py",
        "src/hypervector/research/v39_ht_side_authority_challenger.py",
    }


def _rows(_database: Path, run_id: str) -> tuple[dict[str, object], ...]:
    assert run_id == _RUN_ID
    return (
        {
            "profile_id": PROFILE_ID,
            "profile_fingerprint": PROFILE_FINGERPRINT,
            "observed_at_utc": "2026-08-11T09:00:00-04:00",
            "sequence": 10,
            "payload": {"evaluations": [_evaluation()]},
        },
    )


def _evaluation() -> dict[str, object]:
    return {
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "ETH",
        "decision_time_ms": 1_000,
        "reference_price": 100.0,
        "eligible": True,
        "side": "short",
        "decision_action": "enter_short",
        "readiness": {
            "metrics": {
                "breakout_onset": True,
                "structural_direction": "short",
                "breakout_side": "long",
                "breakout_side_relation": "opposed",
            }
        },
    }


def _load_module() -> ModuleType:
    spec = spec_from_file_location("v39_ht_side_authority_challenger_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
