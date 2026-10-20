"""Cross-run execution-history projection tests for the live cohort."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_cohort_telemetry import (
    AssetCohortSnapshot,
    MultiAssetCohortTelemetry,
    SharedAccountFacts,
)
from hypervector.live.multi_asset_cohort_history import fill_payloads
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


def test_restart_retains_compatible_fill_and_cost_history(tmp_path: Path) -> None:
    """A new run must not hide an exact completed lifecycle from the TUI."""
    config = _config()
    ledgers = _restarted_asset_ledgers(tmp_path, config)
    _append_hype_lifecycle(ledgers["HYPE"])
    current = _reopen_asset_ledgers(ledgers, config, "new-run")
    _append_new_hype_entry(current["HYPE"])
    snapshot = _emit_snapshot(tmp_path, config, current)

    fills = snapshot["recent_fills"]
    assert [fill["trade_id"] for fill in fills] == [101, 102, 103]
    assert fills[1]["origin_run_id"] == "old-run"
    assert fills[1]["strategy_id"] == "hype_breakout_onset_bidirectional_v1"
    assert fills[1]["exit_controller_id"] == "cohort_maximum_hold"
    assert fills[1]["exit_reason"] == "maximum_hold_seconds"
    assert fills[1]["lifecycle_fees_usd"] == pytest.approx(0.021)
    assert fills[1]["lifecycle_funding_usd"] == pytest.approx(0.002)
    assert fills[1]["net_pnl_usd"] == pytest.approx(0.231)
    assert fills[1]["holding_time_ms"] == 1_000
    assert fills[1]["entry_price"] == pytest.approx(100.0)
    assert fills[1]["entry_venue_timestamp_ms"] == 101_000
    assert fills[2]["origin_run_id"] == "new-run"
    assert fills[2]["exit_reason"] is None

    hype = next(asset for asset in snapshot["assets"] if asset["symbol"] == "HYPE")
    assert hype["fees_net_usd"] == pytest.approx(0.031)
    assert hype["funding_net_usd"] == pytest.approx(0.002)
    assert hype["realized_pnl_usd"] == pytest.approx(0.25)
    assert hype["fill_count"] == 3
    assert hype["cost_scope"] == "compatible_profile_history"


def test_split_close_fills_keep_entry_and_exit_controller_attribution(
    tmp_path: Path,
) -> None:
    """Every fill from one close order retains the opened strategy identity."""
    config = _config()
    asset = next(item for item in config.assets if item.symbol == "HYPE")
    ledger = _ledger(tmp_path, asset, "split-close-run")
    _append(
        ledger, "regime_decision", 0, _decision("hype_breakout_onset_bidirectional_v1")
    )
    _append(ledger, "order_intent", 1, _intent("entry", "entry-client", 100.0))
    _append(ledger, "order_acknowledgement", 2, _ack("entry-client", 11))
    _append(
        ledger,
        "fill",
        3,
        _fill_sized(101, 11, 100.0, "B", "Open Long", 0.01, 0.0, 0.5),
    )
    _append(ledger, "regime_decision", 4, _decision("cohort_maximum_hold"))
    _append(ledger, "close", 5, {"reason": "maximum_hold_seconds", "intent": True})
    _append(
        ledger, "order_intent", 6, _intent("reduce_only_close", "exit-client", 101.0)
    )
    _append(ledger, "close", 7, _ack("exit-client", 12))
    _append(
        ledger,
        "fill",
        8,
        _fill_sized(102, 12, 101.0, "A", "Close Long", 0.005, 0.1, 0.2),
    )
    _append(
        ledger,
        "fill",
        9,
        _fill_sized(103, 12, 101.0, "A", "Close Long", 0.007, 0.15, 0.3),
    )
    _append(
        ledger,
        "close",
        10,
        {"reason": "maximum_hold_seconds", "oid": 12, "verified_flat": True},
    )

    closes = [
        fill
        for fill in fill_payloads("HYPE", ledger.read_all())
        if str(fill["direction"]).startswith("Close")
    ]

    assert len(closes) == 2
    assert {fill["strategy_id"] for fill in closes} == {
        "hype_breakout_onset_bidirectional_v1"
    }
    assert {fill["exit_controller_id"] for fill in closes} == {"cohort_maximum_hold"}


def test_target_fill_uses_exact_target_order_context(tmp_path: Path) -> None:
    """A persisted target acknowledgement owns its later venue fill."""
    config = _config()
    asset = next(item for item in config.assets if item.symbol == "BTC")
    ledger = _ledger(tmp_path, asset, "target-run")
    _append(
        ledger, "regime_decision", 0, _decision("hulk_expansion_bidirectional_tuned_v2")
    )
    _append(ledger, "order_intent", 1, _intent("entry", "entry-client", 100.0))
    _append(ledger, "order_acknowledgement", 2, _ack("entry-client", 11))
    _append(ledger, "fill", 3, _fill(101, 11, 100.0, "B", "Open Long", 0.01, 0.0))
    _append(
        ledger,
        "order_intent",
        4,
        {
            "operation": "target",
            "client_order_id": "target-client",
            "limit_price": 103.0,
        },
    )
    _append(
        ledger,
        "target_order",
        5,
        {
            "operation": "target",
            "accepted": True,
            "client_order_id": "target-client",
            "oid": 12,
        },
    )
    _append(
        ledger,
        "target_order",
        7,
        {
            "operation": "target_restart_recovery",
            "accepted": True,
            "client_order_id": "target-client",
            "oid": 12,
        },
    )
    _append(ledger, "fill", 8, _fill(102, 12, 103.0, "A", "Close Long", 0.01, 0.3))
    _append(
        ledger,
        "close",
        9,
        {"reason": "target", "oid": 12, "verified_flat": True},
    )

    close = fill_payloads("BTC", ledger.read_all())[-1]

    assert close["strategy_id"] == "hulk_expansion_bidirectional_tuned_v2"
    assert close["exit_controller_id"] == "hulk_expansion_bidirectional_tuned_v2"
    assert close["operation"] == "target"
    assert close["expected_price"] == pytest.approx(103.0)
    assert close["acknowledgement_latency_ms"] == 1_000
    assert close["exit_reason"] == "target"


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        "tests/fixtures/profiles/cohort_base.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _restarted_asset_ledgers(
    tmp_path: Path,
    config: MultiAssetLiveConfig,
) -> dict[str, SolLiveLedger]:
    return {
        asset.symbol: _ledger(tmp_path, asset, "old-run") for asset in config.assets
    }


def _reopen_asset_ledgers(
    ledgers: dict[str, SolLiveLedger],
    config: MultiAssetLiveConfig,
    run_id: str,
) -> dict[str, SolLiveLedger]:
    assets = {asset.symbol: asset for asset in config.assets}
    return {
        symbol: SolLiveLedger(
            path=ledger.path,
            profile_id=assets[symbol].profile_id,
            profile_fingerprint=assets[symbol].profile_fingerprint,
            run_fingerprint=assets[symbol].run_fingerprint,
            run_id=run_id,
        )
        for symbol, ledger in ledgers.items()
    }


def _ledger(
    tmp_path: Path,
    asset: AssetLiveConfig,
    run_id: str,
) -> SolLiveLedger:
    return SolLiveLedger(
        path=tmp_path
        / "data/live/bidirectional_cohort"
        / f"{asset.symbol.lower()}.jsonl",
        profile_id=asset.profile_id,
        profile_fingerprint=asset.profile_fingerprint,
        run_fingerprint=asset.run_fingerprint,
        run_id=run_id,
    )


def _append_hype_lifecycle(ledger: SolLiveLedger) -> None:
    _append(
        ledger, "regime_decision", 0, _decision("hype_breakout_onset_bidirectional_v1")
    )
    _append(ledger, "order_intent", 1, _intent("entry", "entry-client", 100.0))
    _append(ledger, "order_acknowledgement", 2, _ack("entry-client", 11))
    _append(ledger, "fill", 3, _fill(101, 11, 100.0, "B", "Open Long", 0.01, 0.0))
    _append(
        ledger,
        "funding",
        4,
        {"venue_timestamp_ms": 101_500, "usdc_delta": 0.002},
    )
    _append(ledger, "regime_decision", 5, _decision("cohort_maximum_hold"))
    _append(ledger, "close", 6, {"reason": "maximum_hold_seconds", "intent": True})
    _append(
        ledger, "order_intent", 7, _intent("reduce_only_close", "exit-client", 101.0)
    )
    _append(ledger, "close", 8, _ack("exit-client", 12))
    _append(ledger, "fill", 9, _fill(102, 12, 101.0, "A", "Close Long", 0.011, 0.25))
    _append(
        ledger,
        "close",
        10,
        {"reason": "maximum_hold_seconds", "oid": 12, "verified_flat": True},
    )


def _append_new_hype_entry(ledger: SolLiveLedger) -> None:
    _append(
        ledger, "regime_decision", 11, _decision("hype_breakout_onset_bidirectional_v1")
    )
    _append(ledger, "order_intent", 12, _intent("entry", "new-entry", 102.0))
    _append(ledger, "order_acknowledgement", 13, _ack("new-entry", 13))
    _append(ledger, "fill", 14, _fill(103, 13, 102.0, "B", "Open Long", 0.01, 0.0))


def _decision(strategy_id: str) -> dict[str, object]:
    return {"strategy_id": strategy_id, "reference_price": 100.0}


def _intent(operation: str, client_id: str, mark: float) -> dict[str, object]:
    return {"operation": operation, "client_order_id": client_id, "mark_price": mark}


def _ack(client_id: str, oid: int) -> dict[str, object]:
    return {
        "operation": "entry",
        "accepted": True,
        "client_order_id": client_id,
        "oid": oid,
    }


def _fill(
    trade_id: int,
    oid: int,
    price: float,
    side: str,
    direction: str,
    fee: float,
    pnl: float,
) -> dict[str, object]:
    return _fill_sized(trade_id, oid, price, side, direction, fee, pnl, 0.25)


def _fill_sized(
    trade_id: int,
    oid: int,
    price: float,
    side: str,
    direction: str,
    fee: float,
    pnl: float,
    size: float,
) -> dict[str, object]:
    return {
        "trade_id": trade_id,
        "oid": oid,
        "venue_timestamp_ms": trade_id * 1_000,
        "price": price,
        "size": size,
        "side": side,
        "direction": direction,
        "fee_usd": fee,
        "closed_pnl_usd": pnl,
    }


def _append(
    ledger: SolLiveLedger,
    event_type: str,
    offset: int,
    payload: dict[str, object],
) -> None:
    ledger.append(
        event_type=event_type,
        observed_at_utc=f"2026-08-01T12:00:{offset:02d}+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload=payload,
    )


def _emit_snapshot(
    tmp_path: Path,
    config: MultiAssetLiveConfig,
    asset_ledgers: dict[str, SolLiveLedger],
) -> dict[str, object]:
    cohort = SolLiveLedger(
        path=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="new-run",
    )
    telemetry = MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort,
        asset_ledgers=asset_ledgers,
        now_fn=lambda: datetime(2026, 8, 1, 13, tzinfo=UTC),
    )
    telemetry.emit_snapshot(
        account=SharedAccountFacts(500.0, 500.0, 0.0, 0.0),
        assets=tuple(
            AssetCohortSnapshot(asset.symbol, "FLAT", 0.0, None, None, None)
            for asset in config.assets
        ),
    )
    payload = cohort.read_all()[-1]["payload"]
    assert isinstance(payload, dict)
    return payload
