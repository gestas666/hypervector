"""Tests for the standalone read-only HIP-3 roster sidecar."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError


SCRIPT = Path(__file__).parents[1] / "scripts" / "hip3_roster_observer.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hip3_roster_observer_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Observer:
    """Return one deterministic checkpoint or one explicit failure."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def snapshot(self, observed_at: datetime) -> dict[str, object]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {
            "schema_version": 1,
            "mode": "hip3_roster_observer_checkpoint",
            "status": "available",
            "observed_at_utc": observed_at.isoformat(),
            "active_symbols": ["xyz:SP500"],
            "markets": [{"symbol": "xyz:SP500"}],
            "execution_authority": "none",
            "report_only": True,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "signing_client_constructed": False,
        }


def test_once_writes_available_checkpoint_without_execution_authority(
    tmp_path: Path,
) -> None:
    """A bounded run must durably publish backend-owned read-only telemetry."""
    module = _load_module()
    output = tmp_path / "latest.json"
    observer = _Observer()
    config = module.ObserverConfig(output=output, poll_seconds=1.0, max_polls=1)

    result = module.run_observer(
        config,
        observer=observer,
        clock=lambda: datetime(2026, 8, 6, 16, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert observer.calls == 1
    assert payload["status"] == "available"
    assert payload["lifecycle"] == "stopped"
    assert payload["execution_authority"] == "none"
    assert payload["signing_client_constructed"] is False


def test_failed_once_writes_unavailable_checkpoint_without_fake_market_values(
    tmp_path: Path,
) -> None:
    """A failed venue read must be visible and must not become zero telemetry."""
    module = _load_module()
    output = tmp_path / "latest.json"
    observer = _Observer(ValueError("xyz:GOLD book unavailable"))
    config = module.ObserverConfig(output=output, poll_seconds=1.0, max_polls=1)

    result = module.run_observer(
        config,
        observer=observer,
        clock=lambda: datetime(2026, 8, 6, 16, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert payload["status"] == "unavailable"
    assert payload["markets"] is None
    assert payload["error"]["type"] == "ValueError"
    assert payload["error"]["message"] == "xyz:GOLD book unavailable"
    assert payload["execution_authority"] == "none"


def test_typed_venue_schema_failure_publishes_unavailable_checkpoint(
    tmp_path: Path,
) -> None:
    """Strict SDK parser failures must not terminate without a checkpoint."""
    module = _load_module()
    output = tmp_path / "latest.json"
    observer = _Observer(HyperliquidAdapterError("perp dex schema is invalid"))
    config = module.ObserverConfig(output=output, poll_seconds=1.0, max_polls=1)

    result = module.run_observer(
        config,
        observer=observer,
        clock=lambda: datetime(2026, 8, 6, 16, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert payload["status"] == "unavailable"
    assert payload["error"] == {
        "type": "HyperliquidAdapterError",
        "message": "perp dex schema is invalid",
    }
