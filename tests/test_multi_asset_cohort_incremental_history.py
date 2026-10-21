"""Incremental asset-ledger projection contracts for cohort telemetry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_cohort_models import (
    AssetCohortSnapshot,
    SharedAccountFacts,
)
from hypervector.live.multi_asset_cohort_history_cache import CohortAssetHistoryCache
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import AssetLiveConfig
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_ledger import AssetLiveLedgerError

_RUN_ID = "incremental-history-test"


def test_repeated_snapshots_do_not_rescan_complete_asset_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later snapshot must consume only rows appended after its prior cursor."""
    config, cohort, assets = _runtime(tmp_path)
    _append_book(assets["BTC"], sequence_time=0, mid_price=100.0)
    counts = _count_complete_reads(assets, monkeypatch)
    telemetry = _telemetry(config, cohort, assets)

    _emit_flat_snapshot(telemetry, config)
    _append_book(assets["BTC"], sequence_time=1, mid_price=101.0)
    _emit_flat_snapshot(telemetry, config)

    assert counts == {symbol: 1 for symbol in config.symbols}
    latest = cohort.read_all()[-1]["payload"]
    assert latest["books"] == [_expected_book(mid_price=101.0)]


def test_incremental_snapshot_rejects_asset_ledger_truncation(
    tmp_path: Path,
) -> None:
    """A live asset ledger cannot disappear behind a success-shaped snapshot."""
    config, cohort, assets = _runtime(tmp_path)
    _append_book(assets["BTC"], sequence_time=0, mid_price=100.0)
    telemetry = _telemetry(config, cohort, assets)
    _emit_flat_snapshot(telemetry, config)

    assets["BTC"].path.write_bytes(b"")

    with pytest.raises(AssetLiveLedgerError, match="truncated"):
        _emit_flat_snapshot(telemetry, config)


def test_incremental_book_completes_pending_fill_markout(tmp_path: Path) -> None:
    """The first post-fill book remains available after history compaction."""
    config, cohort, assets = _runtime(tmp_path)
    _append_entry_and_fill(assets["BTC"])
    telemetry = _telemetry(config, cohort, assets)

    _emit_flat_snapshot(telemetry, config)
    assert cohort.read_all()[-1]["payload"]["recent_fills"][0]["markout_bps"] is None
    _append_book(assets["BTC"], sequence_time=6, mid_price=100.2)
    _emit_flat_snapshot(telemetry, config)

    fill = cohort.read_all()[-1]["payload"]["recent_fills"][0]
    assert fill["markout_horizon_ms"] == 6_000
    assert fill["markout_bps"] == pytest.approx(9.99000999)


def test_history_cache_discards_books_unneeded_by_projection(tmp_path: Path) -> None:
    """High-frequency books cannot make cached telemetry history grow unbounded."""
    config, _, assets = _runtime(tmp_path)
    btc = assets["BTC"]
    for offset in range(10):
        _append_book(btc, sequence_time=offset, mid_price=100.0 + offset)

    cache = CohortAssetHistoryCache(assets)
    histories = cache.refresh()

    assert sum(row["event_type"] == "book_observation" for row in histories["BTC"]) == 1
    assert len(histories["ETH"]) == 0
    assert set(histories) == set(config.symbols)


def test_initial_history_projection_does_not_materialize_complete_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial telemetry filters compatible rows during ledger validation."""
    _config, _cohort, assets = _runtime(tmp_path)
    _append_book(assets["BTC"], sequence_time=0, mid_price=100.0)
    for ledger in assets.values():
        monkeypatch.setattr(
            ledger,
            "read_all",
            lambda: pytest.fail("asset history recovery must stream"),
        )

    histories = CohortAssetHistoryCache(assets).refresh()

    assert len(histories["BTC"]) == 1


def _runtime(
    tmp_path: Path,
) -> tuple[MultiAssetLiveConfig, AssetLiveLedger, dict[str, AssetLiveLedger]]:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    root = tmp_path / "data/live/bidirectional_cohort"
    assets = {
        asset.symbol: _ledger(root / f"{asset.symbol.lower()}.jsonl", asset)
        for asset in config.assets
    }
    cohort = AssetLiveLedger(
        path=root / "decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=_RUN_ID,
    )
    return config, cohort, assets


def _ledger(path: Path, asset: AssetLiveConfig) -> AssetLiveLedger:
    return AssetLiveLedger(
        path=path,
        profile_id=asset.profile_id,
        profile_fingerprint=asset.profile_fingerprint,
        run_fingerprint=asset.run_fingerprint,
        run_id=_RUN_ID,
    )


def _telemetry(
    config: MultiAssetLiveConfig,
    cohort: AssetLiveLedger,
    assets: dict[str, AssetLiveLedger],
) -> MultiAssetCohortTelemetry:
    return MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort,
        asset_ledgers=assets,
        now_fn=lambda: datetime(2026, 8, 16, 12, tzinfo=UTC),
    )


def _emit_flat_snapshot(
    telemetry: MultiAssetCohortTelemetry,
    config: MultiAssetLiveConfig,
) -> None:
    telemetry.emit_snapshot(
        account=SharedAccountFacts(5_000.0, 5_000.0, 0.0, 0.0),
        assets=tuple(
            AssetCohortSnapshot(asset.symbol, "FLAT", 0.0, None, None, None)
            for asset in config.assets
        ),
    )


def _count_complete_reads(
    assets: dict[str, AssetLiveLedger],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    counts = {symbol: 0 for symbol in assets}
    for symbol, ledger in assets.items():
        original = ledger.read_matching

        def counted(
            predicate: Callable[[Mapping[str, object]], bool],
            *,
            _symbol: str = symbol,
            _original: Callable[..., list[dict[str, object]]] = original,
            **declared: object,
        ) -> list[dict[str, object]]:
            counts[_symbol] += 1
            return _original(predicate, **declared)

        monkeypatch.setattr(ledger, "read_matching", counted)
    return counts


def _append_book(
    ledger: AssetLiveLedger,
    *,
    sequence_time: int,
    mid_price: float,
) -> None:
    ledger.append(
        event_type="book_observation",
        observed_at_utc=f"2026-08-16T12:00:0{sequence_time}+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            **_expected_book(mid_price=mid_price),
            "exchange_ts_ms": 1_786_882_400_000 + sequence_time * 1_000,
            "recv_ts_ms": 1_786_882_400_000 + sequence_time * 1_000,
        },
    )


def _append_entry_and_fill(ledger: AssetLiveLedger) -> None:
    _append(
        ledger,
        "regime_decision",
        {"strategy_id": "test_strategy", "reference_price": 100.0},
        observed_at="2026-08-16T12:00:00+00:00",
    )
    _append(
        ledger,
        "order_intent",
        {
            "operation": "entry",
            "client_order_id": "0x11111111111111111111111111111111",
            "side": "long",
            "mark_price": 100.0,
        },
        observed_at="2026-08-16T12:00:00+00:00",
    )
    _append_fill_acknowledgement(ledger)


def _append_fill_acknowledgement(ledger: AssetLiveLedger) -> None:
    client_id = "0x11111111111111111111111111111111"
    _append(
        ledger,
        "order_acknowledgement",
        {"accepted": True, "oid": 11, "client_order_id": client_id},
        observed_at="2026-08-16T12:00:00.040000+00:00",
    )
    _append(
        ledger,
        "fill",
        {
            "trade_id": 101,
            "oid": 11,
            "venue_timestamp_ms": 1_786_882_400_000,
            "price": 100.1,
            "size": 1.0,
            "side": "B",
            "direction": "Open Long",
            "fee_usd": 0.045,
            "closed_pnl_usd": 0.0,
        },
        observed_at="2026-08-16T12:00:00.050000+00:00",
    )


def _append(
    ledger: AssetLiveLedger,
    event_type: str,
    payload: dict[str, object],
    *,
    observed_at: str,
) -> None:
    ledger.append(
        event_type=event_type,
        observed_at_utc=observed_at,
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload=payload,
    )


def _expected_book(*, mid_price: float) -> dict[str, object]:
    return {
        "symbol": "BTC",
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": 1_786_882_400_000 + int(mid_price - 100.0) * 1_000,
        "recv_ts_ms": 1_786_882_400_000 + int(mid_price - 100.0) * 1_000,
        "mid_px": mid_price,
        "spread_bps": 1.0,
        "bid_depth_ratio": 1.0,
        "opi": 0.0,
        "bids": [{"price": mid_price - 0.01, "size": 1.0}],
        "asks": [{"price": mid_price + 0.01, "size": 1.0}],
    }
