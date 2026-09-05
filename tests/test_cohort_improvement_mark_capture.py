"""Mark-capture health contracts for the continuous improvement monitor."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"


def test_healthy_index_mark_capture_is_source_bound(tmp_path: Path) -> None:
    """A fresh exact recorder heartbeat must enter the digest as healthy evidence."""
    module = _load()
    path = tmp_path / "status.json"
    path.write_text(json.dumps(_status(1_786_830_000_000_000_000)))

    health = module._load_index_mark_capture(
        path,
        observed_at=datetime.fromtimestamp(1_786_830_030, UTC),
        maximum_age_seconds=90.0,
    )

    assert health.status["status"] == "healthy"
    assert health.status["symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert health.evidence["sha256"]
    assert health.evidence["polls"] == 10
    assert health.evidence["age_seconds"] == 30.0


def test_missing_index_mark_capture_is_explicit(tmp_path: Path) -> None:
    """An absent status must remain visible without pretending evidence exists."""
    module = _load()
    health = module._load_index_mark_capture(
        tmp_path / "missing.json",
        observed_at=datetime.now(UTC),
        maximum_age_seconds=90.0,
    )

    assert health.status["status"] == "unavailable_missing"
    assert health.evidence is None


def test_stale_or_stopped_index_capture_is_not_healthy(tmp_path: Path) -> None:
    """Both stale heartbeats and explicit stops must surface as unavailable."""
    module = _load()
    path = tmp_path / "status.json"
    path.write_text(json.dumps(_status(1_786_830_000_000_000_000)))
    stale = module._load_index_mark_capture(
        path,
        observed_at=datetime.fromtimestamp(1_786_830_100, UTC),
        maximum_age_seconds=90.0,
    )
    stopped_payload = _status(1_786_830_100_000_000_000)
    stopped_payload["event_type"] = "hip3_mark_recorder_stopped"
    path.write_text(json.dumps(stopped_payload))
    stopped = module._load_index_mark_capture(
        path,
        observed_at=datetime.fromtimestamp(1_786_830_101, UTC),
        maximum_age_seconds=90.0,
    )

    assert stale.status["status"] == "unavailable_stale"
    assert stopped.status["status"] == "unavailable_stopped"


def test_tampered_index_capture_contract_is_rejected(tmp_path: Path) -> None:
    """A success-shaped status with execution authority must fail closed."""
    module = _load()
    path = tmp_path / "status.json"
    payload = _status(1_786_830_000_000_000_000)
    payload["execution_authority"] = "hyperliquid_mainnet"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="invalid execution_authority"):
        module._load_index_mark_capture(
            path,
            observed_at=datetime.fromtimestamp(1_786_830_030, UTC),
            maximum_age_seconds=90.0,
        )


def _status(recorded_at_ns: int) -> dict[str, object]:
    return {
        "event_type": "hip3_mark_recorder_heartbeat",
        "symbols": ["xyz:SP500", "xyz:SPCX"],
        "source": "hyperliquid_info_metaAndAssetCtxs",
        "poll_seconds": 3.0,
        "polls": 10,
        "rows_by_symbol": {"xyz:SP500": 10, "xyz:SPCX": 10},
        "recorded_at_ns": recorded_at_ns,
        "execution_authority": "none",
        "report_only": True,
        "signing_client_constructed": False,
        "orders_supported": False,
    }


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_improvement_monitor_mark_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
