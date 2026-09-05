"""Tests for immutable V58 BTC descriptive regime evidence publication."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from hypervector.data.oxa_candles import (
    OxaCandle,
    OxaCandleFetch,
    OxaCandlePage,
    OxaCandleRequest,
    store_candle_history,
)

_SCRIPT = Path("scripts/v58_btc_liquidation_regime_evidence.py")


def _load() -> ModuleType:
    spec = spec_from_file_location("v58_btc_liquidation_regime_evidence", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load BTC liquidation regime evidence command")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source_bundle(tmp_path: Path) -> tuple[Path, OxaCandleRequest]:
    start = datetime(2025, 11, 30, tzinfo=UTC)
    rows = 300
    end = start + timedelta(minutes=5 * rows)
    request = OxaCandleRequest("BTC", start, end, "5m", 10_000, 1)
    candles = tuple(
        _candle(start + timedelta(minutes=5 * row), row) for row in range(rows)
    )
    raw_rows = [_raw_row(candle) for candle in candles]
    raw = {
        "success": True,
        "data": raw_rows,
        "meta": {"request_id": "regime-test-page", "next_cursor": None},
    }
    page = OxaCandlePage("regime-test-page", None, candles, raw)
    result = OxaCandleFetch((page,), candles, True, None)
    stored = store_candle_history(tmp_path, request, result)
    return stored.directory, request


def _candle(timestamp: datetime, row: int) -> OxaCandle:
    price = 90_000.0 + row
    return OxaCandle(
        timestamp.isoformat().replace("+00:00", "Z"),
        int(timestamp.timestamp() * 1000),
        price,
        price + 2.0,
        price - 2.0,
        price + 1.0,
        10.0 + row,
        (10.0 + row) * price,
        row + 1,
    )


def _raw_row(candle: OxaCandle) -> dict[str, object]:
    return {
        "timestamp": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "quote_volume": candle.quote_volume,
        "trade_count": candle.trade_count,
    }


def test_publication_is_immutable_descriptive_and_source_bound(tmp_path: Path) -> None:
    """Published labels expose no execution authority or outcome calculation."""
    bundle, request = _source_bundle(tmp_path)
    output = tmp_path / "regime-evidence"
    evaluation_start = pd.Timestamp(request.start) + timedelta(minutes=5 * 240)
    module = _load()

    module.publish_regime_evidence(
        candle_bundle=bundle,
        output=output,
        request=request,
        evaluation_start=evaluation_start,
        evaluation_end=pd.Timestamp(request.end),
        minimum_context_bars=240,
    )

    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    labels = pd.read_parquet(output / "labels.parquet")
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["market_returns_computed"] is False
    assert report["contract"]["regime_labels_are_entry_gates"] is False
    assert report["source_evidence"]["raw_reproduction_matches"] is True
    assert report["summary"]["label_rows"] == 300
    assert len(labels) == 300
    assert set(manifest["files"]) == {"labels.parquet", "report.json"}

    try:
        module.publish_regime_evidence(
            candle_bundle=bundle,
            output=output,
            request=request,
            evaluation_start=evaluation_start,
            evaluation_end=pd.Timestamp(request.end),
            minimum_context_bars=240,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("immutable regime evidence was overwritten")
