"""Tests for the standalone read-only HIP-3 roster sidecar."""

from __future__ import annotations

from datetime import UTC, datetime
from collections.abc import Mapping
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.research.hip3_roster_observer import ACTIVE_HIP3_MARKETS
from test_hip3_roster_observer import _Reader


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


def test_default_observer_wires_shared_funding_into_real_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI must actually connect funding instead of leaving an optional source empty."""
    module = _load_module()
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    calls: list[tuple[str, ...]] = []

    def sources(
        *, symbols: tuple[str, ...], environ: Mapping[str, str]
    ) -> SimpleNamespace:
        """Return same-client source-shaped fixtures with no network capability."""
        calls.append(symbols)
        return SimpleNamespace(
            readers=readers,
            funding=SimpleNamespace(snapshot=lambda: dict.fromkeys(readers, 0.0000125)),
        )

    monkeypatch.setattr(
        module, "create_read_only_hip3_roster_sources", sources, raising=False
    )
    monkeypatch.setattr(
        module,
        "create_read_only_hip3_roster_readers",
        lambda **_kwargs: readers,
        raising=False,
    )
    observer, _archived = module._build_observer()
    result = observer.snapshot(datetime(2026, 9, 11, 14, 0, tzinfo=UTC))
    assert all(
        row["venue"]["funding_rate_hourly"] == 0.0000125 for row in result["markets"]
    )
    assert calls == [tuple(readers)]


def test_parser_enables_durable_research_history_by_default() -> None:
    """The launched observer must enable capture without undocumented extra wiring."""
    module = _load_module()
    config = module.config_from_args(module.build_parser().parse_args([]))
    assert getattr(config, "context_history", None) == Path(
        "data/research/hip3_asset_context"
    )


def test_capture_wiring_reuses_one_request_for_telemetry_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete CLI poll archives real context fields through the shared reader."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader
    from test_hip3_roster_funding import _Info

    module = _load_module()
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    response = [
        {"universe": [{"name": symbol} for symbol in readers]},
        [
            {
                "funding": "0.0001",
                "premium": "0.001",
                "markPx": "100.1",
                "oraclePx": "100",
            }
            for _ in readers
        ],
    ]
    info = _Info(response)
    sources = SimpleNamespace(
        readers=readers,
        funding=Hip3RosterFundingReader(info=info, symbols=tuple(readers)),
    )
    monkeypatch.setattr(
        module, "create_read_only_hip3_roster_sources", lambda **_: sources
    )
    assert "context_history" in module.ObserverConfig.__dataclass_fields__
    observer, _archived = module._build_observer(context_history=tmp_path)
    result = observer.snapshot(datetime.now(UTC))
    assert result["status"] == "available"
    assert len(info.calls) == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_failed_poll_records_one_gap_without_repeating_it_at_shutdown(
    tmp_path: Path,
) -> None:
    """A failed endpoint poll remains explicit in the public research timeline."""
    module = _load_module()
    assert "context_history" in module.ObserverConfig.__dataclass_fields__
    config = module.ObserverConfig(
        output=tmp_path / "latest.json",
        max_polls=1,
        context_history=tmp_path / "history",
    )
    module.run_observer(config, observer=_Observer(ValueError("unavailable")))
    rows = [
        json.loads(line)
        for p in config.context_history.glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["status"] == "unavailable"
    assert rows[0]["markets"] is None
    assert rows[0]["error_type"] == "ValueError"


def test_research_archive_failure_never_stops_roster_telemetry(
    tmp_path: Path,
) -> None:
    """A report-only archive must not take down the supervisor's fee evidence.

    `_publish` wrote the gap record outside any handler, so one torn JSONL tail
    turned into an unrecoverable launchd crash loop while the roster checkpoint
    still looked fresh on disk.
    """
    module = _load_module()
    history = tmp_path / "history"
    history.mkdir()
    (history / (datetime.now(UTC).date().isoformat() + ".jsonl")).write_text(
        '{"partial":'
    )
    config = module.ObserverConfig(
        output=tmp_path / "roster.json", context_history=history
    )
    payload = {"status": "unavailable", "error": {"type": "ServerError"}}

    module._publish(config, payload, lifecycle="running", polls=1)

    assert json.loads((tmp_path / "roster.json").read_text())["status"] == (
        "unavailable"
    )


def test_an_archived_poll_is_not_also_recorded_as_a_gap(tmp_path: Path) -> None:
    """The capture runs first; a later per-market failure is not a missing poll."""
    module = _load_module()
    history = tmp_path / "history"
    config = module.ObserverConfig(
        output=tmp_path / "roster.json", context_history=history
    )
    payload = {"status": "unavailable", "error": {"type": "ServerError"}}

    module._publish(
        config, payload, lifecycle="running", polls=1, archived=True
    )
    assert not list(history.glob("*.jsonl"))

    module._publish(
        config, payload, lifecycle="running", polls=2, archived=False
    )
    rows = [
        json.loads(line)
        for path in history.glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert [row["status"] for row in rows] == ["unavailable"]
