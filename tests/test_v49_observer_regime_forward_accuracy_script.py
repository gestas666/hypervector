"""Acceptance for the immutable v49 observer regime diagnostic."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v49_observer_regime_forward_accuracy.py")


def test_script_publishes_cross_restart_authority_none_evidence(
    tmp_path: Path,
) -> None:
    """The command must preserve exact compatible observer continuity."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    output = tmp_path / "regime.json"
    rows = [
        *_run("observer-1", 0, (100.0, 101.0)),
        *_run("observer-2", 2, (101.0, 99.0)),
    ]
    ledger.write_text(
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows),
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        [
            "--ledger",
            str(ledger),
            "--run-id",
            "observer-1",
            "--horizons-minutes",
            "1",
            "--out",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.publish_report(output, report)

    assert report["source"]["compatible_run_ids"] == ["observer-1", "observer-2"]
    assert report["execution_authority"] == "none"
    assert report["material_state_sha256"]
    assert output.exists()
    with pytest.raises(FileExistsError):
        module.publish_report(output, report)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v49 observer regime forward accuracy script is missing")
    spec = spec_from_file_location("v49_observer_regime_accuracy_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v49 observer regime script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    run_id: str, start_minute: int, prices: tuple[float, float]
) -> list[dict[str, object]]:
    return [
        _row(run_id, "configuration_identity", start_minute, _identity()),
        *[
            _row(
                run_id,
                "intent_routing",
                minute,
                {"evaluations": [_evaluation(minute, price)]},
            )
            for minute, price in zip(
                range(start_minute + 1, start_minute + 3), prices, strict=True
            )
        ],
    ]


def _row(
    run_id: str, event_type: str, minute: int, values: dict[str, object]
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": run_id,
        "observed_at_utc": f"1970-01-01T00:{minute:02}:01+00:00",
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "v49",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "payload": values,
    }


def _identity() -> dict[str, object]:
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "profile_fingerprint": "profile",
    }


def _evaluation(minute: int, price: float) -> dict[str, object]:
    return {
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "SOL",
        "decision_time_ms": minute * 60_000,
        "reference_price": price,
        "eligible": False,
        "side": "long",
        "primary_regime": "TREND_UP",
        "state_1m": "TREND_UP",
        "state_5m": "TREND_UP",
        "context_15m": "TREND_UP",
        "readiness": {"side": "long", "blockers": ["waiting"], "metrics": {}},
    }
