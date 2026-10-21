"""Exact execution-quality projection tests for the shared cohort."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hypervector.live.multi_asset_cohort_telemetry import (
    AssetCohortSnapshot,
    MultiAssetCohortTelemetry,
    SharedAccountFacts,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.asset_ledger import AssetLiveLedger

_RUN_ID = "cohort-live-fill-test"
_CLIENT_ORDER_ID = "0x11111111111111111111111111111111"


def test_snapshot_projects_fill_slippage_latency_and_markout(tmp_path: Path) -> None:
    """Execution quality is derived in backend telemetry rather than the TUI."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    asset_ledgers = _asset_ledgers(config, tmp_path)
    _seed_fill_lifecycle(asset_ledgers["BTC"])
    cohort_ledger = _cohort_ledger(config, tmp_path)
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort_ledger,
        asset_ledgers=asset_ledgers,
        now_fn=lambda: datetime(2026, 8, 1, 12, 1, tzinfo=UTC),
    )

    telemetry.emit_snapshot(
        account=SharedAccountFacts(150.0, 145.0, 5.0, 25.0),
        assets=tuple(
            AssetCohortSnapshot(asset.symbol, "FLAT", 0.0, None, None, None)
            for asset in config.assets
        ),
    )

    payload = cohort_ledger.read_all()[0]["payload"]
    _assert_fill(payload["recent_fills"][0])
    assert payload["books"][0]["symbol"] == "BTC"
    assert payload["books"][0]["bids"][0]["price"] == 100.19


def _asset_ledgers(
    config: MultiAssetLiveConfig,
    tmp_path: Path,
) -> dict[str, AssetLiveLedger]:
    return {
        asset.symbol: AssetLiveLedger(
            path=tmp_path
            / "data/live/bidirectional_cohort"
            / f"{asset.symbol.lower()}.jsonl",
            profile_id=asset.profile_id,
            profile_fingerprint=asset.profile_fingerprint,
            run_fingerprint=asset.run_fingerprint,
            run_id=_RUN_ID,
        )
        for asset in config.assets
    }


def _cohort_ledger(config: MultiAssetLiveConfig, tmp_path: Path) -> AssetLiveLedger:
    return AssetLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=_RUN_ID,
    )


def _seed_fill_lifecycle(ledger: AssetLiveLedger) -> None:
    _seed_entry_identity(ledger)
    _seed_fill_and_book(ledger)


def _seed_entry_identity(ledger: AssetLiveLedger) -> None:
    _append(
        ledger,
        "regime_decision",
        "2026-08-01T12:00:00+00:00",
        {
            "strategy_id": "test_breakout_1m",
            "reference_price": 100.0,
        },
    )
    _append(
        ledger,
        "order_intent",
        "2026-08-01T12:00:00+00:00",
        {
            "operation": "entry",
            "client_order_id": _CLIENT_ORDER_ID,
            "side": "long",
            "mark_price": 100.0,
        },
    )
    _append(
        ledger,
        "order_acknowledgement",
        "2026-08-01T12:00:00.040000+00:00",
        {
            "accepted": True,
            "oid": 11,
            "client_order_id": _CLIENT_ORDER_ID,
        },
    )


def _seed_fill_and_book(ledger: AssetLiveLedger) -> None:
    _append(
        ledger,
        "fill",
        "2026-08-01T12:00:00.050000+00:00",
        {
            "trade_id": 101,
            "oid": 11,
            "venue_timestamp_ms": 1_785_585_600_050,
            "price": 100.1,
            "size": 0.25,
            "side": "B",
            "direction": "Open Long",
            "fee_usd": 0.011,
            "closed_pnl_usd": 0.0,
        },
    )
    _append(
        ledger,
        "book_observation",
        "2026-08-01T12:00:06+00:00",
        {
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": 1_785_585_606_050,
            "recv_ts_ms": 1_785_585_606_060,
            "mid_px": 100.2,
            "spread_bps": 1.0,
            "bid_depth_ratio": 1.5,
            "opi": 0.2,
            "bids": [{"price": 100.19, "size": 3.0}],
            "asks": [{"price": 100.21, "size": 2.0}],
        },
    )


def _append(
    ledger: AssetLiveLedger,
    event_type: str,
    observed_at_utc: str,
    payload: dict[str, object],
) -> None:
    ledger.append(
        event_type=event_type,
        observed_at_utc=observed_at_utc,
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload=payload,
    )


def _assert_fill(fill: dict[str, object]) -> None:
    assert fill["strategy_id"] == "test_breakout_1m"
    assert fill["trade_id"] == 101
    assert fill["acknowledgement_latency_ms"] == 40
    assert abs(float(fill["slippage_bps"]) - 10.0) < 1e-9
    assert fill["markout_horizon_ms"] == 6_000
    assert abs(float(fill["markout_bps"]) - 9.99000999) < 1e-6
