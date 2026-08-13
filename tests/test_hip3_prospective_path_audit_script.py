"""Prospective HIP-3 path-audit command tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "hip3_prospective_path_audit.py"
_START_MS = 1_800_000_000_000
_BAR_MS = 15 * 60_000
_SYMBOL = "xyz:SKHX"


class _Archive:
    """Deterministic read-only event archive."""

    def replay_l2(self) -> tuple[L2SnapshotEvent, ...]:
        return tuple(_book(offset) for offset in range(0, _BAR_MS, 10_000))

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        return (_trade(30_000),)

    def replay_asset_contexts(self) -> tuple[AssetContextEvent, ...]:
        return tuple(_mark(offset) for offset in range(0, _BAR_MS, 5_000))

    def replay_gaps(self) -> tuple[StreamGap, ...]:
        return ()


def test_command_writes_authority_none_exact_symbol_report(tmp_path: Path) -> None:
    module = _load_module()
    output = tmp_path / "audit.json"
    args = module.build_parser().parse_args(
        ["--symbol", "xyz:skhx", "--data-root", str(tmp_path), "--output", str(output)]
    )

    report = module.run_command(
        args,
        archive=_Archive(),
        observed_at_ms=_START_MS + _BAR_MS,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == report
    assert report["source"]["symbol"] == _SYMBOL
    assert report["source"]["archive_path"] == str(
        tmp_path / "cache/events/hyperliquid" / _SYMBOL
    )
    assert report["technical_assessment"]["prospective_bar_path_coverage_resolved"]
    assert report["contract"]["execution_authority"] == "none"
    assert set(report["generator_identity"]) == {
        "scripts/hip3_prospective_path_audit.py",
        "src/hypervector/research/hip3_prospective_path_audit.py",
    }
    assert all(
        len(value["sha256"]) == 64 for value in report["generator_identity"].values()
    )


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hip3_prospective_path_audit_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _level(price: float) -> BookLevel:
    return BookLevel(price=price, size=1.0, order_count=1)


def _book(offset_ms: int) -> L2SnapshotEvent:
    timestamp = _START_MS + offset_ms
    return L2SnapshotEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 1_000,
        (_level(99.0),),
        (_level(101.0),),
    )


def _mark(offset_ms: int) -> AssetContextEvent:
    timestamp = _START_MS + offset_ms
    return AssetContextEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 2_000,
        100.0,
        100.1,
        0.00001,
        10_000.0,
        100.0,
    )


def _trade(offset_ms: int) -> PublicTradeEvent:
    timestamp = _START_MS + offset_ms
    return PublicTradeEvent(
        _SYMBOL,
        "buy",
        100.0,
        1.0,
        "0x1",
        timestamp,
        timestamp * 1_000_000 + 3_000,
        1,
        "buyer",
        "seller",
    )
