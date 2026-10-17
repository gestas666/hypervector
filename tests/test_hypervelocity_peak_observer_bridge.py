"""One-way integration tests for report-only peak observer telemetry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from dataclasses import replace
from test_paper_session import _write_strict_export
from typing import Literal

import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.book import BookFeed
from hypervector.paper.costs import CostProvider
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.hypervelocity_session_bridge import (
    HypervelocitySessionBridge,
    ShadowLedgerContext,
)
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.paper.peak_protection_observer import (
    PEAK_OBSERVER_CANDIDATE_ID,
    PeakObserverConfig,
    PeakProtectionObserver,
)
from hypervector.paper.session import PaperSession
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState

BASE_MS = 1_785_103_200_000


def _iso(offset_ms: int) -> str:
    """Return a deterministic UTC timestamp."""
    return datetime.fromtimestamp((BASE_MS + offset_ms) / 1_000, tz=UTC).isoformat()


def _l2(offset_ms: int, *, bid: float = 64_500.0) -> L2SnapshotEvent:
    """Return one fresh complete BTC book."""
    exchange_ms = BASE_MS + offset_ms
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        bids=(BookLevel(bid, 0.001, 1),),
        asks=(BookLevel(bid + 1.0, 1.0, 1),),
    )


def _trade(offset_ms: int) -> PublicTradeEvent:
    """Return a maker-entry-filling sell-aggressor trade."""
    exchange_ms = BASE_MS + offset_ms
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side="sell",
        price=64_500.0,
        size=0.05,
        transaction_hash="0xobserver",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        trade_id=71,
        buyer="0xbuyer",
        seller="0xseller",
    )


def _market(
    offset_ms: int,
    direction: Literal["long"] | None = "long",
    maximum_hold_seconds: float | None = None,
) -> RuntimeMarketState:
    """Return one classified long entry decision."""
    return RuntimeMarketState(
        symbol="BTC",
        observed_at=_iso(offset_ms),
        entry_direction=direction,
        structural_direction=direction,
        entry_quantity=0.04,
        entry_limit_price=64_500.0 if direction is not None else None,
        evidence_fresh=True,
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        target_price_fraction=0.002,
        price_tick=1.0,
        maximum_hold_seconds=maximum_hold_seconds,
    )


def _observer(mode: Literal["off", "observe"]) -> PeakProtectionObserver:
    """Return the frozen candidate in the requested telemetry mode."""
    return PeakProtectionObserver(
        config=PeakObserverConfig(
            mode=mode,
            candidate_id=PEAK_OBSERVER_CANDIDATE_ID,
            activation_margin_pct=7.0,
            lock_ratio=0.55,
            minimum_stop_move_fraction=0.0005,
            update_cooldown_seconds=60.0,
            sample_interval_seconds=5.0,
            execution_authority="none",
        ),
        leverage=40.0,
        taker_fee_rate=0.00045,
    )


def _bridge(
    root: Path,
    mode: Literal["off", "observe"],
) -> HypervelocitySessionBridge:
    """Return a deterministic event bridge with optional observer telemetry."""
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=10_000.0,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=0,
            cancel_latency_ms=50,
            update_latency_ms=0,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=40.0,
        maintenance_rate=0.0125,
        max_event_age_ms=3_000,
    )
    controller = HypervelocityShadowController(
        port=port,
        initial_market=_market(0, None),
    )
    engine = ExplicitFillEngine(
        root,
        cost_provider=CostProvider(fee_tier=0, slippage_bps=0.0),
        run_id="observer-run",
        export_id="observer-export",
        strategy_name="hypervelocity_1m_scalper",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        execution_mode="shadow",
    )
    return HypervelocitySessionBridge(
        controller=controller,
        engine=engine,
        data_root=root,
        book_feed=BookFeed("BTC", max_age_ms=3_000),
        context=ShadowLedgerContext(
            run_id="observer-run",
            export_id="observer-export",
            strategy_name="hypervelocity_1m_scalper",
            symbol="BTC",
            timeframe="1m",
        ),
        peak_observer=_observer(mode),
    )


def _open_long(bridge: HypervelocitySessionBridge) -> None:
    """Fill one deterministic maker long through the public event path."""
    bridge.ingest(_l2(0))
    bridge.on_market(_market(1))
    bridge.ingest(_l2(2))
    assert bridge.ingest(_trade(3)) == "enter_long"


def _rows(root: Path) -> list[dict[str, object]]:
    """Return every durable test-ledger row."""
    path = root / "paper" / "decisions" / "decisions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def _profile_session(
    root: Path, offset_ms: int
) -> tuple[PaperSession, HypervelocitySessionBridge]:
    """Attach the configured event runtime to a persistent paper root."""
    profile = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")
    profile = replace(profile, metalabel_mode="off", export_path=_write_strict_export(root, strategy="hypervelocity_1m_scalper_long"))
    session = PaperSession(
        export_dir=profile.export_path,
        data_root=root,
        execution_mode="shadow",
        hypervelocity_profile=profile,
    )
    session.activate_hypervelocity_event_runtime(observed_at=_iso(offset_ms))
    session.ensure_session_identity()
    bridge = session._event_shadow_bridge
    assert bridge is not None
    return session, bridge


def _open_profile_long(bridge: HypervelocitySessionBridge) -> None:
    """Fill a profile-latency maker long through the configured bridge."""
    bridge.ingest(_l2(0))
    bridge.on_market(_market(1))
    bridge.ingest(_l2(100))
    assert bridge.ingest(_trade(101)) == "enter_long"


def test_observer_cannot_change_controller_or_portfolio_outcome(tmp_path: Path) -> None:
    """Observed and disabled bridges remain execution-equivalent."""
    observed = _bridge(tmp_path / "observed", "observe")
    disabled = _bridge(tmp_path / "disabled", "off")
    for bridge in (observed, disabled):
        _open_long(bridge)
        bridge.ingest(_l2(4_000, bid=64_612.0))
        assert bridge.apply_mark(mark_price=64_613.0, observed_at=_iso(4_001)) is None
        bridge.ingest(_l2(9_000, bid=64_555.0))
        assert bridge.apply_mark(mark_price=64_556.0, observed_at=_iso(9_001)) is None

    assert observed.controller.state == disabled.controller.state
    assert observed.controller.port.account_snapshot() == (
        disabled.controller.port.account_snapshot()
    )
    assert observed.controller.port.execution_records() == (
        disabled.controller.port.execution_records()
    )
    observer_rows = [
        row for row in _rows(tmp_path / "observed") if row["action"].startswith("peak_")
    ]
    assert [row["action"] for row in observer_rows] == [
        "peak_observer_position_start",
        "peak_observer_armed",
        "peak_observer_would_exit",
    ]
    exit_row = observer_rows[-1]
    assert exit_row["hypothetical_exit_price"] == pytest.approx(64_555.0)
    assert exit_row["hypothetical_exit_fee_usd"] == pytest.approx(
        0.04 * 64_555.0 * 0.00045
    )
    assert exit_row["execution_authority"] == "none"
    assert exit_row["report_only"] is True
    assert exit_row["submitted"] is False
    assert exit_row["place_attempted"] is False


def test_maximum_hold_exit_is_taker_ledger_close_with_explicit_reason(
    tmp_path: Path,
) -> None:
    """The event-port deadline fill closes the same durable portfolio ledger."""
    bridge = _bridge(tmp_path / "maximum-hold", "off")
    bridge.ingest(_l2(0))
    bridge.on_market(_market(1, maximum_hold_seconds=0.010))
    bridge.ingest(_l2(2))
    assert bridge.ingest(_trade(3)) == "enter_long"

    assert bridge.ingest(_l2(13)) == "close"

    fills = [
        row for row in _rows(tmp_path / "maximum-hold") if row["action"] == "close"
    ]
    assert len(fills) == 1
    assert fills[0]["exit_reason"] == "maximum_hold_24h"
    assert fills[0]["liquidity_side"] == "taker"
    assert fills[0]["fill_model_id"] == "fresh_bbo_taker_v1"
    assert fills[0]["order_intent"]["order_type"] == "market"
    assert fills[0]["order_intent"]["time_in_force"] == "ioc"
    assert fills[0]["order_intent"]["reduce_only"] is True
    assert bridge.controller.state.position_quantity == 0.0


def test_stale_book_cannot_price_hypothetical_exit(tmp_path: Path) -> None:
    """A triggered observer records missing coverage rather than a fake price."""
    bridge = _bridge(tmp_path / "stale", "observe")
    _open_long(bridge)
    bridge.ingest(_l2(4_000, bid=64_612.0))
    bridge.apply_mark(mark_price=64_613.0, observed_at=_iso(4_001))

    assert bridge.apply_mark(mark_price=64_556.0, observed_at=_iso(10_001)) is None

    trigger = _rows(tmp_path / "stale")[-1]
    assert trigger["action"] == "peak_observer_trigger_unpriced"
    assert trigger["trigger_evidence_status"] == "stale_or_missing_book"
    assert trigger["coverage_complete_since_entry"] is False
    assert trigger["hypothetical_exit_price"] is None
    assert bridge.controller.state.position_quantity == pytest.approx(0.04)


def test_session_restores_observer_state_without_duplicate_start(
    tmp_path: Path,
) -> None:
    """A normal backend restart retains the causal peak and locked stop."""
    root = tmp_path / "restart"
    first, first_bridge = _profile_session(root, 0)
    _open_profile_long(first_bridge)
    first_bridge.ingest(_l2(4_000, bid=64_656.0))
    first.apply_hyperliquid_mark(mark_price=64_657.0, observed_at=_iso(4_001))

    resumed, resumed_bridge = _profile_session(root, 5_000)
    resumed_bridge.ingest(_l2(9_000, bid=64_555.0))
    action = resumed.apply_hyperliquid_mark(
        mark_price=64_556.0,
        observed_at=_iso(9_001),
    )

    observer_rows = [
        row for row in _rows(root) if row["action"].startswith("peak_observer_")
    ]
    assert action is None
    assert [row["action"] for row in observer_rows] == [
        "peak_observer_position_start",
        "peak_observer_armed",
        "peak_observer_would_exit",
    ]
    assert observer_rows[-1]["coverage_complete_since_entry"] is True
    assert resumed.engine.position.qty == pytest.approx(0.04)
