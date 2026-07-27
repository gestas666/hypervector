"""Paper session: loadout → bar walk → intent → ExplicitFillEngine.

Offline multi-bar walk and incremental ``on_bar`` for the live daemon share
the same alpha path. No Nautilus node, no venue orders. Funding uses the
configured/last hourly rate offline; optional live refresh is opt-in.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from hypervector.data.book_record import append_book_snapshot
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.infra import ensure_data_layout
from hypervector.nautilus.actor import (
    DEFAULT_MAX_LOOKBACK,
    _action_from_intent,
    _append_bar_record,
    _stop_tp_fracs,
)
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.signals import last_bar_intent
from hypervector.nautilus.sizing import position_size_frac
from hypervector.paper.book import (
    DEFAULT_MAX_BOOK_AGE_MS,
    BookFeed,
    BookSnapshot,
    summarize_book,
)
from hypervector.paper.book_gate import (
    DEFAULT_MAX_SPREAD_BPS,
    DEFAULT_MIN_IMBALANCE,
    DEFAULT_MIN_TOUCH_SIZE,
    evaluate_book_entry,
)
from hypervector.paper.conviction import (
    DEFAULT_METALABEL_MIN_P,
    ConvictionProvider,
    ConvictionResult,
    DirectionalMetalabelConvictionProvider,
    FixedConvictionProvider,
    MetalabelConvictionProvider,
    MetalabelMode,
    resolve_metalabel_mode,
)
from hypervector.paper.costs import CostProvider
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.hypervelocity_session_bridge import (
    HypervelocitySessionBridge,
    ShadowLedgerContext,
    ShadowOrderAnnotation,
)
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)
from hypervector.paper.event_runtime import build_event_shadow_controller
from hypervector.paper.event_resume import PendingTargetResume
from hypervector.paper.ledger import DECISIONS_FILENAME, append_paper_decision
from hypervector.paper.liquidation_execution import (
    LIQUIDATION_EXECUTION_MODEL,
    PARTIAL_LIQUIDATION_SUPPORTED,
)
from hypervector.paper.maker_execution import (
    PostOnlyLimitFillModel,
    PendingMakerEntry,
    entry_limit_price,
    entry_was_filled,
    hyperliquid_price_tick,
    quantize_size_down,
    round_price_to_tick,
    target_was_filled,
)
from hypervector.paper.resume import (
    ShadowPortfolioResume,
    load_shadow_portfolio_resume,
    portfolio_fingerprint,
)
from hypervector.paper.telemetry import bar_telemetry_payload, book_telemetry_payload
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)
from hypervector.strategies.hypervelocity import (
    current_hypervelocity_entry_allowed,
    current_hypervelocity_market,
    current_hypervelocity_regime,
)
from hypervector.strategies.hypervelocity_profile import HypervelocityProfile
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState
from hypervector.strategies import register_all_strategies

logger = logging.getLogger(__name__)

_OHLCV_REQUIRED = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class PaperSessionResult:
    """Outcome of a paper session walk (offline or daemon summary)."""

    run_id: str
    decisions_path: Path
    bars_processed: int
    fills_count: int
    export_dir: Path


class PaperSession:
    """Incremental paper bar processor (warm-up + live share this path)."""

    def __init__(
        self,
        *,
        export_dir: Path | str,
        data_root: Path | str,
        conviction: float = 0.5,
        fee_tier: int = 0,
        sandbox_enabled: bool = False,
        run_id: str | None = None,
        funding_rate_hourly: float | None = None,
        enable_funding_refresh: bool = False,
        preferred_fill_model: str = FILL_MODEL_L2_WALK_V1,
        max_book_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS,
        book_feed: BookFeed | None = None,
        enable_book_poll: bool = False,
        book_gate_enabled: bool = True,
        book_max_spread_bps: float = DEFAULT_MAX_SPREAD_BPS,
        book_min_touch_size: float = DEFAULT_MIN_TOUCH_SIZE,
        book_min_imbalance: float = DEFAULT_MIN_IMBALANCE,
        metalabel_enabled: bool = False,
        metalabeler: Any | None = None,
        metalabel_min_p: float = DEFAULT_METALABEL_MIN_P,
        metalabel_filter: bool = True,
        metalabel_mode: str | None = None,
        conviction_provider: ConvictionProvider | None = None,
        execution_mode: str = "paper",
        hypervelocity_profile: HypervelocityProfile | None = None,
        lookback_days: int | None = None,
    ) -> None:
        register_all_strategies()
        export_path = Path(export_dir)
        if not export_path.is_dir():
            raise FileNotFoundError(f"export_dir not found: {export_path}")

        self.loadout = load_strategy_loadout(export_path, strict=True)
        self._is_hypervelocity = is_hypervelocity_strategy(self.loadout.strategy_name)
        self.hypervelocity_profile = hypervelocity_profile
        self.lookback_days = lookback_days
        if hypervelocity_profile is not None and not self._is_hypervelocity:
            raise ValueError("Hypervelocity profile requires a Hypervelocity export")
        if self._is_hypervelocity and (
            self.loadout.symbol != "BTC" or self.loadout.timeframe != "1m"
        ):
            raise ValueError("faithful Hypervelocity paper execution requires BTC 1m")
        self.root = Path(data_root)
        self.paths = ensure_data_layout(self.root)
        self.decisions_path = self.paths.paper_decisions / DECISIONS_FILENAME
        self.conviction = float(conviction)
        self.sandbox_enabled = bool(sandbox_enabled)
        self.enable_funding_refresh = bool(enable_funding_refresh)
        self.enable_book_poll = bool(enable_book_poll)
        self.book_gate_enabled = bool(book_gate_enabled) and not self._is_hypervelocity
        self.book_max_spread_bps = float(book_max_spread_bps)
        self.book_min_touch_size = float(book_min_touch_size)
        self.book_min_imbalance = float(book_min_imbalance)
        self.max_book_age_ms = float(max_book_age_ms)
        self.preferred_fill_model = str(preferred_fill_model)
        requested_metalabel_mode = (
            hypervelocity_profile.metalabel_mode
            if hypervelocity_profile is not None
            else metalabel_mode
        )
        self.metalabel_mode = resolve_metalabel_mode(
            enabled=(
                hypervelocity_profile.metalabel_mode != "off"
                if hypervelocity_profile is not None
                else bool(metalabel_enabled)
            ),
            filter_entries=bool(metalabel_filter),
            requested=requested_metalabel_mode,
        )
        if self._is_hypervelocity and self.metalabel_mode in ("scale", "filter"):
            self.metalabel_mode = "observe"
        self.metalabel_enabled = self.metalabel_mode != "off"
        self.metalabel_min_p = float(metalabel_min_p)
        self.metalabel_filter = self.metalabel_mode == "filter"
        self.execution_mode = str(execution_mode)
        if (
            hypervelocity_profile is not None
            and self.metalabel_mode == "observe"
            and conviction_provider is None
            and metalabeler is None
        ):
            self.conviction_provider = _build_hypervelocity_directional_provider(
                hypervelocity_profile,
                conviction=self.conviction,
                metalabel_min_p=self.metalabel_min_p,
            )
        else:
            self.conviction_provider = _build_conviction_provider(
                conviction=self.conviction,
                metalabel_enabled=self.metalabel_enabled,
                metalabeler=metalabeler,
                metalabel_min_p=self.metalabel_min_p,
                metalabel_filter=self.metalabel_filter,
                metalabel_mode=self.metalabel_mode,
                conviction_provider=conviction_provider,
                data_root=self.root,
            )

        self.strategy_name = (
            hypervelocity_profile.strategy_id
            if hypervelocity_profile is not None
            else self.loadout.strategy_name
        )
        self._portfolio_spec = _portfolio_spec(
            self.loadout,
            profile=hypervelocity_profile,
            strategy_name=self.strategy_name,
        )
        self._portfolio_fingerprint = portfolio_fingerprint(self._portfolio_spec)
        resume = self._load_shadow_resume()
        self._shadow_resume: ShadowPortfolioResume | None = resume
        self.run_id = (
            resume.run_id if resume is not None else (run_id or uuid.uuid4().hex[:12])
        )
        self.export_id = self.loadout.run_id or export_path.name
        self.cost_provider = _cost_provider_from_loadout(
            self.loadout,
            fee_tier=(
                hypervelocity_profile.fee_tier if hypervelocity_profile else fee_tier
            ),
            funding_rate_hourly=funding_rate_hourly,
        )
        if hypervelocity_profile is not None:
            self.cost_provider.slippage_bps = hypervelocity_profile.slippage_bps
            self.cost_provider.funding_poll_secs = (
                hypervelocity_profile.funding_refresh_seconds
            )
        self.book_feed = (
            book_feed
            if book_feed is not None
            else BookFeed(self.loadout.symbol, max_age_ms=self.max_book_age_ms)
        )
        self.equity = (
            resume.init_cash
            if resume is not None
            else (
                float(self.loadout.init_cash)
                if self.loadout.init_cash is not None
                else 10_000.0
            )
        )
        self.engine = ExplicitFillEngine(
            self.root,
            cost_provider=self.cost_provider,
            run_id=self.run_id,
            export_id=str(self.export_id),
            strategy_name=self.strategy_name,
            symbol=self.loadout.symbol,
            timeframe=self.loadout.timeframe,
            conviction=self.conviction,
            sandbox_enabled=self.sandbox_enabled,
            preferred_fill_model=self.preferred_fill_model,
            max_book_age_ms=self.max_book_age_ms,
            execution_mode=self.execution_mode,
            init_cash=float(self.equity),
        )
        if resume is not None:
            self.engine.restore_position(
                qty=resume.position_qty,
                avg_px=resume.position_avg_px,
                realized_pnl=resume.realized_pnl,
                init_cash=resume.init_cash,
            )
        self._event_shadow_bridge: HypervelocitySessionBridge | None = None
        self.exits = _exits_dict(self.loadout)
        self.buffer_rows: list[dict[str, Any]] = []
        self.fills_count = 0
        self.bars_processed = 0
        self._last_ts: pd.Timestamp | None = None
        self._last_funding_refresh_mono: float = 0.0
        self._identity_written = False
        self._pending_maker_entry = _restore_pending_maker_entry(resume)
        self._reconciled_through: pd.Timestamp | None = None
        event_authority = (
            hypervelocity_profile is not None
            and hypervelocity_profile.shadow_execution_model == "nautilus_event_v1"
        )
        self._downtime_reconciliation_enabled = (
            not event_authority
            and resume is not None
            and (
                self.engine.position.qty != 0.0 or self._pending_maker_entry is not None
            )
        )
        self._live_telemetry_enabled = False
        self._live_activated_at: pd.Timestamp | None = None
        self._last_hypervelocity_exit_at = (
            pd.Timestamp(resume.last_exit_at)
            if resume and resume.last_exit_at
            else None
        )
        self._expired_entry_direction = (
            resume.expired_entry_direction if resume is not None else None
        )
        self._completed_trade_direction = (
            resume.completed_trade_direction if resume is not None else None
        )

    def _load_shadow_resume(self) -> ShadowPortfolioResume | None:
        """Return persistent Hypervelocity state for normal shadow restarts."""
        if not self._is_hypervelocity or self.execution_mode != "shadow":
            return None
        return load_shadow_portfolio_resume(
            self.decisions_path,
            symbol=self.loadout.symbol,
            timeframe=self.loadout.timeframe,
            expected_spec=self._portfolio_spec,
        )

    @property
    def pending_maker_entry(self) -> PendingMakerEntry | None:
        """Return the current backend-owned pending maker entry, if any."""
        if self._event_shadow_bridge is not None:
            return self._event_shadow_bridge.pending_maker_entry
        return self._pending_maker_entry

    def _current_liquidation_price(self) -> float | None:
        """Return the attached event backend's isolated liquidation boundary."""
        bridge = self._event_shadow_bridge
        return bridge.liquidation_price if bridge is not None else None

    def attach_hypervelocity_event_controller(
        self,
        controller: HypervelocityShadowController,
    ) -> None:
        """Attach the no-submit event runtime after validating portfolio parity."""
        if not self._is_hypervelocity or self.execution_mode != "shadow":
            raise RuntimeError("event shadow controller requires Hypervelocity shadow")
        expected = controller.state.position_quantity
        if controller.state.position_direction == "short":
            expected = -expected
        if not math.isclose(self.engine.position.qty, expected, abs_tol=1e-10):
            raise RuntimeError("cannot attach event runtime with mismatched position")
        self._event_shadow_bridge = HypervelocitySessionBridge(
            controller=controller,
            engine=self.engine,
            data_root=self.root,
            book_feed=self.book_feed,
            context=ShadowLedgerContext(
                run_id=self.run_id,
                export_id=str(self.export_id),
                strategy_name=self.strategy_name,
                symbol=self.loadout.symbol,
                timeframe=self.loadout.timeframe,
            ),
        )
        self._restore_event_annotations()

    def _restore_event_annotations(self) -> None:
        bridge = self._event_shadow_bridge
        resume = self._shadow_resume
        pending = resume.pending_entry if resume is not None else None
        if bridge is None or resume is None:
            return
        inherited = None
        if pending is not None and pending.client_order_id is not None:
            inherited = ShadowOrderAnnotation(
                conviction=(
                    pending.conviction
                    if pending.conviction is not None
                    else self.conviction
                ),
                conviction_source=pending.conviction_source or "fixed",
                metalabel_p=pending.metalabel_p,
                metalabel_bundle_id=pending.metalabel_bundle_id,
            )
            bridge.seed_order_annotation(pending.client_order_id, inherited)
        self._seed_target_annotations(bridge, resume, inherited)

    def _seed_target_annotations(
        self,
        bridge: HypervelocitySessionBridge,
        resume: ShadowPortfolioResume,
        inherited: ShadowOrderAnnotation | None,
    ) -> None:
        """Restore report-only context for every durable target."""
        for target in resume.active_targets:
            bridge.seed_order_annotation(
                target.client_order_id,
                _target_resume_annotation(target, inherited, self.conviction),
            )

    def activate_hypervelocity_event_runtime(
        self,
        *,
        observed_at: str,
    ) -> HypervelocityShadowController:
        """Construct and attach the profile-authoritative event shadow runtime."""
        profile = self.hypervelocity_profile
        if profile is None:
            raise RuntimeError("event shadow activation requires a validated profile")
        controller = build_event_shadow_controller(
            profile=profile,
            initial_cash_usd=self.engine.initial_cash,
            observed_at=observed_at,
            resume=self._shadow_resume,
        )
        self.attach_hypervelocity_event_controller(controller)
        return controller

    def ingest_hyperliquid_event(
        self,
        event: L2SnapshotEvent | PublicTradeEvent | AssetContextEvent | StreamGap,
    ) -> str | None:
        """Consume one public event through the attached backend shadow runtime."""
        bridge = self._event_shadow_bridge
        if bridge is None:
            raise RuntimeError("Hypervelocity event shadow runtime is not attached")
        self.ensure_session_identity()
        if isinstance(event, AssetContextEvent):
            return self._ingest_asset_context(event)
        action = bridge.ingest(event)
        if isinstance(event, L2SnapshotEvent) and self._live_telemetry_enabled:
            snapshot = self.book_feed.latest()
            if snapshot is not None:
                self._record_book_telemetry(snapshot)
        self.fills_count += bridge.last_fill_count
        return action

    def _ingest_asset_context(self, event: AssetContextEvent) -> str | None:
        """Update live costs and apply a continuous no-submit venue mark."""
        if event.symbol != self.loadout.symbol:
            raise ValueError(
                f"asset context symbol {event.symbol!r} != {self.loadout.symbol!r}"
            )
        observed_at = pd.Timestamp(
            event.received_ts_ns,
            unit="ns",
            tz="UTC",
        ).isoformat()
        self.cost_provider.observe_market_context(
            funding_rate_hourly=event.funding_rate_hourly,
            oracle_px=event.oracle_price,
            observed_at=observed_at,
        )
        return self.apply_hyperliquid_mark(
            mark_price=event.mark_price,
            observed_at=observed_at,
        )

    def apply_hyperliquid_mark(
        self,
        *,
        mark_price: float,
        observed_at: str,
    ) -> str | None:
        """Apply one backend venue mark to the attached isolated shadow runtime."""
        bridge = self._event_shadow_bridge
        if bridge is None:
            raise RuntimeError("Hypervelocity event shadow runtime is not attached")
        action = bridge.apply_mark(mark_price=mark_price, observed_at=observed_at)
        if action is not None:
            self.fills_count += 1
        return action

    @property
    def downtime_reconciliation_enabled(self) -> bool:
        """Return whether restart began with an active target or maker entry."""
        return self._downtime_reconciliation_enabled

    @property
    def event_downtime_funding_enabled(self) -> bool:
        """Return whether a restored event position needs missed funding."""
        return (
            self._event_shadow_bridge is not None
            and self._shadow_resume is not None
            and self.engine.position.qty != 0.0
        )

    @property
    def resume_state_asof(self) -> str | None:
        """Return the persisted market-state timestamp used for replay splitting."""
        return (
            self._shadow_resume.state_asof if self._shadow_resume is not None else None
        )

    def inject_book(self, snap: BookSnapshot) -> None:
        """Inject a BookSnapshot for offline tests (no network)."""
        self.book_feed.update(snap)

    def enable_live_telemetry(
        self, *, activated_at: pd.Timestamp | None = None
    ) -> None:
        """Enable report-only per-bar telemetry after historical warm-up."""
        self._live_telemetry_enabled = True
        self._live_activated_at = activated_at

    @property
    def last_timestamp(self) -> pd.Timestamp | None:
        return self._last_ts

    def maybe_refresh_funding(self) -> float | None:
        """Refresh live funding rate when enabled (throttled). Offline-safe no-op.

        Returns the new rate, or None if skipped / failed.
        """
        if not self.enable_funding_refresh:
            return None
        now = time.monotonic()
        poll = float(self.cost_provider.funding_poll_secs)
        if (
            self._last_funding_refresh_mono > 0.0
            and (now - self._last_funding_refresh_mono) < poll
        ):
            return None
        try:
            rate = self.cost_provider.refresh_funding(self.loadout.symbol)
        except Exception as exc:
            logger.warning(
                "funding refresh failed for %s: %s", self.loadout.symbol, exc
            )
            return None
        self._last_funding_refresh_mono = now
        return rate

    def initialize_hypervelocity_venue(self) -> float:
        """Fetch and validate current venue precision, leverage, and funding."""
        if self.hypervelocity_profile is None:
            raise ValueError("validated Hypervelocity profile is required")
        state = self.cost_provider.refresh_market_state(self.loadout.symbol)
        profile = self.hypervelocity_profile
        if state.size_decimals != profile.size_decimals:
            raise RuntimeError("live size_decimals differs from Hypervelocity config")
        if state.max_leverage < profile.leverage:
            raise RuntimeError("live venue max leverage is below strategy leverage")
        self._last_funding_refresh_mono = time.monotonic()
        return state.funding_rate_hourly

    def on_bar(self, row: pd.Series | dict[str, Any]) -> str | None:
        """Process one OHLCV bar. Returns fill action or None.

        When a position is open, applies one hour of signed funding at bar close
        using the current ``cost_provider`` rate (no network in this method).
        """
        self.ensure_session_identity()
        record = _row_to_buffer_record(
            row if isinstance(row, pd.Series) else pd.Series(row)
        )
        _append_bar_record(self.buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK)
        self.bars_processed += 1
        ts = record.get("timestamp")
        if isinstance(ts, pd.Timestamp):
            self._last_ts = ts

        self.maybe_refresh_funding()

        event_funding_applied = self._event_shadow_bridge is not None
        if event_funding_applied:
            self._apply_hourly_funding(record)
        liquidation_action = self._apply_event_mark(record)

        if self._is_hypervelocity and self._live_telemetry_enabled:
            self._record_hypervelocity_regime(record)

        fill_action: str | None = None
        if len(self.buffer_rows) >= 2:
            fill_action = self._process_intent(record)

        if self._is_hypervelocity and self._live_telemetry_enabled:
            self._record_hypervelocity_entry_execution(record)

        if not event_funding_applied:
            self._apply_hourly_funding(record)
        return fill_action or liquidation_action

    def _apply_hourly_funding(self, record: dict[str, Any]) -> None:
        """Apply funding only on an hourly Hyperliquid settlement boundary."""
        if self.engine.position.qty == 0.0 or not _is_funding_boundary(
            record, timeframe=self.loadout.timeframe
        ):
            return
        snapshot = self.cost_provider.snapshot()
        oracle_px = snapshot.oracle_px or float(record["close"])
        applied_at = _bar_close_timestamp(
            record, timeframe=self.loadout.timeframe
        ).isoformat()
        if self._event_shadow_bridge is not None:
            self._event_shadow_bridge.apply_funding(
                hourly_rate=snapshot.funding_rate_hourly,
                oracle_price=oracle_px,
                applied_at=applied_at,
            )
            return
        self.engine.apply_funding(
            feed_ts=applied_at,
            oracle_px=oracle_px,
            hours=1.0,
        )

    def _apply_event_mark(self, record: dict[str, Any]) -> str | None:
        """Apply the latest public oracle mark only for event authority."""
        if self._event_shadow_bridge is None:
            return None
        snapshot = self.cost_provider.snapshot()
        return self.apply_hyperliquid_mark(
            mark_price=snapshot.oracle_px or float(record["close"]),
            observed_at=self._event_decision_timestamp(record).isoformat(),
        )

    def _record_hypervelocity_regime(self, record: dict[str, Any]) -> None:
        """Append the causal regime state used by the live entry decision."""
        frame = _buffer_to_df(self.buffer_rows)
        payload = self._hypervelocity_regime_payload(frame)
        payload.update(bar_telemetry_payload(frame, record))
        payload["funding_rate_hourly"] = (
            self.cost_provider.snapshot().funding_rate_hourly
        )
        append_paper_decision(
            self.root,
            {
                "feed_ts": self._hypervelocity_feed_ts(record),
                "run_id": self.run_id,
                "export_id": self.export_id,
                "strategy_name": self.strategy_name,
                "symbol": self.loadout.symbol,
                "timeframe": self.loadout.timeframe,
                "action": "regime_observation",
                **payload,
                "execution_mode": self.execution_mode,
                "submitted": False,
                "place_attempted": False,
                "position_qty": float(self.engine.position.qty),
                "position_avg_px": float(self.engine.position.avg_px),
                "liquidation_price": self._current_liquidation_price(),
                "mark_px": float(record["close"]),
                "realized_pnl": float(self.engine.position.realized_pnl),
                "unrealized_pnl": float(
                    self.engine.position.qty
                    * (float(record["close"]) - self.engine.position.avg_px)
                ),
                "equity": float(self.engine.equity(mark_px=float(record["close"]))),
            },
        )

    def _record_hypervelocity_entry_execution(self, record: dict[str, Any]) -> None:
        """Publish entry execution state after the current bar is processed."""
        append_paper_decision(
            self.root,
            {
                "feed_ts": self._hypervelocity_feed_ts(record),
                "run_id": self.run_id,
                "export_id": self.export_id,
                "strategy_name": self.strategy_name,
                "symbol": self.loadout.symbol,
                "timeframe": self.loadout.timeframe,
                "action": "entry_execution_observation",
                **self._hypervelocity_entry_execution_payload(record),
                "execution_mode": self.execution_mode,
                "submitted": False,
                "place_attempted": False,
            },
        )

    def _hypervelocity_entry_execution_payload(
        self, record: dict[str, Any]
    ) -> dict[str, str | bool | None]:
        """Return backend-owned maker, retry, and cooldown display state."""
        pending = self.pending_maker_entry
        retry_state = self._hypervelocity_retry_state()
        return {
            "maker_entry_state": "pending" if pending is not None else "standby",
            "maker_entry_direction": pending.direction if pending is not None else None,
            "entry_retry_state": retry_state,
            "entry_cooldown_active": self._hypervelocity_reentry_cooling_down(record),
        }

    def _hypervelocity_retry_state(self) -> str:
        """Return why a flat strategy may not retry the current direction."""
        completed = self._completed_trade_direction
        expired = self._expired_entry_direction
        if self._event_shadow_bridge is not None:
            state = self._event_shadow_bridge.controller.state
            completed = state.completed_trade_direction
            expired = state.expired_entry_direction
        if completed is not None:
            return f"awaiting_regime_reset_{completed}"
        if expired is not None:
            return f"blocked_{expired}"
        return "ready"

    def _hypervelocity_regime_payload(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Return the exact backend classification fields used for display."""
        if self.hypervelocity_profile is None:
            direction = self._hypervelocity_direction()
            legacy = current_hypervelocity_regime(frame, direction=direction)
            market = current_hypervelocity_market(frame)
            return {
                "primary_regime": legacy.primary_regime,
                "breakout_direction": legacy.breakout_direction,
                "entry_direction": legacy.direction,
                "entry_allowed": legacy.entry_allowed,
                "state_1m": market.state_1m,
                "state_5m": market.state_5m,
                "context_15m": market.context_15m,
                "confidence": market.confidence,
                "regime_strength_score": market.regime_strength_score,
                "regime_score_source": market.regime_score_source,
                "regime_reason": market.reason,
            }
        market = current_hypervelocity_market(
            frame,
            regime_config=self.hypervelocity_profile.regime_config,
        )
        return {
            "primary_regime": market.primary_regime,
            "breakout_direction": market.breakout_direction,
            "entry_direction": market.entry_direction,
            "entry_allowed": market.entry_direction is not None,
            "state_1m": market.state_1m,
            "state_5m": market.state_5m,
            "context_15m": market.context_15m,
            "confidence": market.confidence,
            "regime_strength_score": market.regime_strength_score,
            "regime_score_source": market.regime_score_source,
            "regime_reason": market.reason,
        }

    def refresh_book_telemetry(self) -> BookSnapshot | None:
        """Poll L2 once and publish a no-submit backend telemetry observation."""
        if not self.enable_book_poll:
            return None
        snapshot = self.book_feed.poll()
        if snapshot is None:
            return None
        profile = self.hypervelocity_profile
        if profile is not None and profile.orderbook_archive_enabled:
            append_book_snapshot(
                self.root,
                snapshot,
                depth_levels=profile.orderbook_archive_depth_levels,
                run_id=self.run_id,
            )
        if self._is_hypervelocity and self._live_telemetry_enabled:
            self._record_book_telemetry(snapshot)
        return snapshot

    def _record_book_telemetry(self, snapshot: BookSnapshot) -> None:
        """Append measured book levels and derived microstructure metrics."""
        try:
            metrics = summarize_book(snapshot)
        except ValueError as exc:
            logger.warning(
                "invalid book telemetry for %s: %s", self.loadout.symbol, exc
            )
            return
        append_paper_decision(
            self.root,
            book_telemetry_payload(
                snapshot=snapshot,
                metrics=metrics,
                run_id=self.run_id,
                export_id=str(self.export_id),
                strategy_name=self.strategy_name,
                execution_mode=self.execution_mode,
                timeframe=self.loadout.timeframe,
            ),
        )

    def _process_intent(self, record: dict[str, Any]) -> str | None:
        """Map strategy intent on the latest bar into a market fill, if any."""
        if self._is_hypervelocity:
            return self._process_hypervelocity(record)
        return self._process_standard_intent(record)

    def _process_standard_intent(self, record: dict[str, Any]) -> str | None:
        """Apply the existing immediate-fill path for non-Hypervelocity strategies."""
        df = _buffer_to_df(self.buffer_rows)
        try:
            intent = last_bar_intent(
                df, self.loadout.strategy_name, dict(self.loadout.params)
            )
        except Exception:
            # Match actor: skip bar on signal failure rather than abort session.
            return None

        pos = self.engine.position
        is_flat = pos.qty == 0.0
        if is_flat:
            position_side: str | None = None
        elif pos.qty > 0:
            position_side = "long"
        else:
            position_side = "short"

        action = _action_from_intent(
            intent, is_flat=is_flat, position_side=position_side
        )
        if action == "hold":
            return None

        mark_px = float(record["close"])
        feed_ts = _feed_ts(record)
        intent_payload = {
            "direction": intent.direction,
            "enter": intent.enter,
            "exit": intent.exit,
            "bar_index": intent.bar_index,
        }

        # Live path: refresh book so the gate uses current L2, not a stale cache.
        if self.enable_book_poll:
            self.book_feed.poll()
        book = self.book_feed.latest()
        # Metalabel: scale conviction by p; optionally filter entries (skip low p).
        cv = self.conviction_provider.resolve(bars=df)
        cv_kwargs = _conviction_fill_kwargs(cv)

        if action == "close":
            # Exits are never book/ML-filtered — always allow risk-off.
            qty = abs(float(pos.qty))
            if qty <= 0:
                return None
            side = "sell" if pos.qty > 0 else "buy"
            rec = self.engine.apply_market_fill(
                feed_ts=feed_ts,
                action="close",
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
                book=book,
                **cv_kwargs,
            )
            if not rec.get("skipped"):
                self.fills_count += 1
                return action
            return None

        if action in ("enter_long", "enter_short"):
            side = "buy" if action == "enter_long" else "sell"
            # Book gate: whether we fire (not only how we fill).
            if self.book_gate_enabled:
                import time as _time

                now_ms = _time.time() * 1000.0
                # Require fresh book on live feed; offline warm-up may lack L2.
                require_fresh = bool(self.enable_book_poll)
                gate = evaluate_book_entry(
                    book,
                    side=side,
                    now_ms=now_ms,
                    max_age_ms=self.max_book_age_ms,
                    max_spread_bps=self.book_max_spread_bps,
                    min_touch_size=self.book_min_touch_size,
                    min_imbalance=self.book_min_imbalance,
                    require_fresh=require_fresh,
                )
                if not gate.allow:
                    logger.info(
                        "book gate skip %s: %s metrics=%s",
                        action,
                        gate.reason,
                        gate.metrics,
                    )
                    append_paper_decision(
                        self.root,
                        {
                            "feed_ts": feed_ts,
                            "action": action,
                            "side": side,
                            "qty": 0.0,
                            "fill_qty": 0.0,
                            "mark_px": mark_px,
                            "skipped": True,
                            "skip_reason": gate.reason or "book_gate",
                            "book_gate": gate.metrics,
                            "intent": intent_payload,
                            "execution_mode": self.execution_mode,
                            "run_id": self.run_id,
                            "export_id": self.export_id,
                            **cv_kwargs,
                        },
                    )
                    return None

            if not cv.allow_entry:
                logger.info(
                    "metalabel filter skip %s: %s (p=%s)",
                    action,
                    cv.skip_reason,
                    cv.metalabel_p,
                )
                append_paper_decision(
                    self.root,
                    {
                        "feed_ts": feed_ts,
                        "action": action,
                        "side": "buy" if action == "enter_long" else "sell",
                        "qty": 0.0,
                        "fill_qty": 0.0,
                        "mark_px": mark_px,
                        "skipped": True,
                        "skip_reason": cv.skip_reason or "metalabel_filter",
                        "metalabel_allow_entry": False,
                        "intent": intent_payload,
                        "execution_mode": self.execution_mode,
                        "run_id": self.run_id,
                        "export_id": self.export_id,
                        **cv_kwargs,
                    },
                )
                return None
            qty = _entry_qty(
                df=df,
                loadout=self.loadout,
                exits=self.exits,
                equity=self.engine.equity(mark_px=mark_px),
                conviction=cv.conviction,
                mark_px=mark_px,
            )
            if qty is None or qty <= 0:
                return None
            rec = self.engine.apply_market_fill(
                feed_ts=feed_ts,
                action=action,
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
                book=book,
                **cv_kwargs,
            )
            if not rec.get("skipped"):
                self.fills_count += 1
                return action
            return None

        return None

    def _process_hypervelocity(self, record: dict[str, Any]) -> str | None:
        """Advance causal maker entry and fixed-target state for Hypervelocity."""
        if self._event_shadow_bridge is not None:
            return self._process_hypervelocity_event(record)
        book = self._usable_book(record)
        if self.engine.position.qty != 0.0:
            return self._fill_hypervelocity_target(record, book)
        direction = self._desired_hypervelocity_direction()
        self._observe_entry_direction(direction)
        allowed = direction is not None
        pending = self._pending_maker_entry
        if pending is not None and pending.direction != direction:
            self._cancel_pending(record, "canonical_regime_direction_changed")
        elif pending is not None and self._pending_expired(pending, record):
            self._expire_pending(record, "entry_ttl_expired")
        elif pending is not None and entry_was_filled(
            pending,
            record,
            book=book,
            tick_size=self._hypervelocity_tick(pending.limit_price),
        ):
            return self._fill_pending_entry(record, book)
        if (
            self._pending_maker_entry is None
            and allowed
            and direction is not None
            and direction != self._expired_entry_direction
            and direction != self._completed_trade_direction
            and not self._hypervelocity_reentry_cooling_down(record)
        ):
            self._submit_pending_entry(record, direction, book)
        return None

    def _process_hypervelocity_event(self, record: dict[str, Any]) -> str | None:
        """Submit classified intent to the event runtime without claiming a fill."""
        bridge = self._event_shadow_bridge
        if bridge is None:
            raise RuntimeError("Hypervelocity event shadow runtime is not attached")
        frame = _buffer_to_df(self.buffer_rows)
        direction = self._desired_hypervelocity_direction()
        market = self._event_market_state(record, frame, direction)
        annotation = self._event_order_annotation(frame, direction)
        return bridge.on_market(market, annotation=annotation)

    def _event_market_state(
        self,
        record: dict[str, Any],
        frame: pd.DataFrame,
        direction: str | None,
    ) -> RuntimeMarketState:
        """Build one causal decision from regime state and fresh event evidence."""
        bridge = self._event_shadow_bridge
        if bridge is None:
            raise RuntimeError("Hypervelocity event shadow runtime is not attached")
        mark_px = float(record["close"])
        size_decimals = (
            self.hypervelocity_profile.size_decimals
            if self.hypervelocity_profile is not None
            else 5
        )
        quantity = self._event_entry_quantity(frame, mark_px, size_decimals)
        decision_at = self._event_decision_timestamp(record)
        book = self._usable_book_at(decision_at)
        limit = (
            entry_limit_price(direction, record, book=book)
            if direction is not None
            else None
        )
        profile = self.hypervelocity_profile
        contract = HypervelocityContract()
        return RuntimeMarketState(
            symbol=self.loadout.symbol,
            observed_at=decision_at.isoformat(),
            entry_direction=direction,
            entry_quantity=max(quantity, 10 ** (-size_decimals)),
            entry_limit_price=limit,
            evidence_fresh=bridge.controller.port.evidence_fresh,
            entry_ttl_seconds=(
                profile.entry_ttl_seconds
                if profile is not None
                else contract.entry_ttl_seconds
            ),
            reentry_cooldown_seconds=float(
                (profile.reentry_cooldown_bars if profile is not None else 1)
                * _timeframe_minutes(self.loadout.timeframe)
                * 60
            ),
            target_price_fraction=contract.target_price_fraction,
            price_tick=self._hypervelocity_tick(mark_px),
        )

    def _event_entry_quantity(
        self,
        frame: pd.DataFrame,
        mark_px: float,
        size_decimals: int,
    ) -> float:
        """Return fixed-contract size; model annotations cannot scale it."""
        qty = _entry_qty(
            df=frame,
            loadout=self.loadout,
            exits=self.exits,
            equity=self.engine.equity(mark_px=mark_px),
            conviction=self.conviction,
            mark_px=mark_px,
        )
        return quantize_size_down(qty or 0.0, size_decimals=size_decimals)

    def _event_order_annotation(
        self,
        frame: pd.DataFrame,
        direction: str | None,
    ) -> ShadowOrderAnnotation | None:
        """Resolve report-only model context without filtering or scaling."""
        if direction is None:
            return None
        resolved = self.conviction_provider.resolve(bars=frame, direction=direction)
        return ShadowOrderAnnotation(
            conviction=resolved.conviction,
            conviction_source=resolved.source,
            metalabel_p=resolved.metalabel_p,
            metalabel_bundle_id=resolved.metalabel_bundle_id,
        )

    def _observe_entry_direction(self, direction: str | None) -> None:
        """Re-arm consumed entry episodes after a non-matching regime."""
        if (
            self._expired_entry_direction is not None
            and direction != self._expired_entry_direction
        ):
            self._expired_entry_direction = None
        if (
            self._completed_trade_direction is not None
            and direction != self._completed_trade_direction
        ):
            self._completed_trade_direction = None

    def _expire_pending(self, record: dict[str, Any], reason: str) -> None:
        """Cancel an expired maker and consume its directional regime episode."""
        pending = self._pending_maker_entry
        if pending is None:
            return
        direction = pending.direction
        self._cancel_pending(record, reason)
        self._expired_entry_direction = direction

    def _hypervelocity_reentry_cooling_down(self, record: dict[str, Any]) -> bool:
        """Return whether the explicit minimum completed-bar pause remains."""
        profile = self.hypervelocity_profile
        last_exit = self._last_hypervelocity_exit_at
        if self._event_shadow_bridge is not None:
            value = self._event_shadow_bridge.controller.state.last_exit_at
            last_exit = pd.Timestamp(value) if value is not None else None
        if profile is None or last_exit is None:
            return False
        elapsed = self._hypervelocity_timestamp(record) - last_exit
        required = pd.Timedelta(
            minutes=(
                profile.reentry_cooldown_bars
                * _timeframe_minutes(self.loadout.timeframe)
            )
        )
        return elapsed < required

    def _fill_hypervelocity_target(
        self,
        record: dict[str, Any],
        book: BookSnapshot | None,
    ) -> str | None:
        position = self.engine.position
        direction = "long" if position.qty > 0.0 else "short"
        contract = HypervelocityContract()
        multiplier = 1.0 + contract.target_price_fraction
        if direction == "short":
            multiplier = 1.0 - contract.target_price_fraction
        raw_target = float(position.avg_px) * multiplier
        target = round_price_to_tick(
            raw_target,
            tick_size=self._hypervelocity_tick(raw_target),
            upward=direction == "long",
        )
        if not target_was_filled(
            direction=direction,
            target_price=target,
            record=record,
            book=book,
            tick_size=self._hypervelocity_tick(target),
        ):
            return None
        side = "sell" if direction == "long" else "buy"
        rec = self.engine.apply_market_fill(
            feed_ts=self._hypervelocity_feed_ts(record),
            action="close",
            side=side,
            qty=abs(float(position.qty)),
            mark_px=target,
            book=book,
            fill_model=PostOnlyLimitFillModel(),
            exit_reason=f"take_profit_{contract.target_margin_pct:g}pct_margin",
        )
        if rec.get("skipped"):
            return None
        self._last_hypervelocity_exit_at = self._hypervelocity_timestamp(record)
        self._completed_trade_direction = direction
        self.fills_count += 1
        return "close"

    def _fill_pending_entry(
        self,
        record: dict[str, Any],
        book: BookSnapshot | None,
    ) -> str | None:
        pending = self._pending_maker_entry
        if pending is None:
            return None
        rec = self.engine.apply_market_fill(
            feed_ts=self._hypervelocity_feed_ts(record),
            action=pending.action,
            side=pending.side,
            qty=pending.qty,
            mark_px=pending.limit_price,
            book=book,
            fill_model=PostOnlyLimitFillModel(),
            conviction=pending.conviction,
            conviction_source=pending.conviction_source,
            metalabel_p=pending.metalabel_p,
            metalabel_bundle_id=pending.metalabel_bundle_id,
        )
        if rec.get("skipped"):
            return None
        self._pending_maker_entry = None
        self.fills_count += 1
        return pending.action

    def _submit_pending_entry(
        self,
        record: dict[str, Any],
        direction: str,
        book: BookSnapshot | None,
    ) -> None:
        df = _buffer_to_df(self.buffer_rows)
        mark_px = float(record["close"])
        qty = _entry_qty(
            df=df,
            loadout=self.loadout,
            exits=self.exits,
            equity=self.engine.equity(mark_px=mark_px),
            conviction=self.conviction,
            mark_px=mark_px,
        )
        size_decimals = (
            self.hypervelocity_profile.size_decimals
            if self.hypervelocity_profile
            else 5
        )
        qty = quantize_size_down(qty or 0.0, size_decimals=size_decimals)
        if qty <= 0.0:
            return
        limit = entry_limit_price(direction, record, book=book)
        submitted_at = self._hypervelocity_timestamp(record)
        cv = self.conviction_provider.resolve(bars=df, direction=direction)
        self._pending_maker_entry = PendingMakerEntry(
            direction=direction,
            qty=qty,
            limit_price=limit,
            submitted_at=submitted_at,
            conviction=cv.conviction,
            conviction_source=cv.source,
            metalabel_p=cv.metalabel_p,
            metalabel_bundle_id=cv.metalabel_bundle_id,
        )
        side = "buy" if direction == "long" else "sell"
        self.engine.record_order_event(
            feed_ts=self._hypervelocity_feed_ts(record),
            action="submit_entry",
            side=side,
            qty=qty,
            limit_px=limit,
            status="pending",
            **_conviction_fill_kwargs(cv),
        )

    def _cancel_pending(self, record: dict[str, Any], reason: str) -> None:
        pending = self._pending_maker_entry
        if pending is None:
            return
        self.engine.record_order_event(
            feed_ts=self._hypervelocity_feed_ts(record),
            action="cancel_entry",
            side=pending.side,
            qty=pending.qty,
            limit_px=pending.limit_price,
            status="canceled",
            reason=reason,
        )
        self._pending_maker_entry = None

    def _hypervelocity_allowed(self, direction: str) -> bool:
        frame = _buffer_to_df(self.buffer_rows)
        if self.hypervelocity_profile is None:
            return current_hypervelocity_entry_allowed(frame, direction=direction)
        return current_hypervelocity_entry_allowed(
            frame,
            direction=direction,
            regime_config=self.hypervelocity_profile.regime_config,
        )

    def _desired_hypervelocity_direction(self) -> str | None:
        if self.hypervelocity_profile is None:
            direction = self._hypervelocity_direction()
            return direction if self._hypervelocity_allowed(direction) else None
        observation = current_hypervelocity_market(
            _buffer_to_df(self.buffer_rows),
            regime_config=self.hypervelocity_profile.regime_config,
        )
        return observation.entry_direction

    def _hypervelocity_direction(self) -> str:
        return "short" if self.loadout.strategy_name.endswith("_short") else "long"

    def _hypervelocity_tick(self, price: float) -> float:
        size_decimals = (
            self.hypervelocity_profile.size_decimals
            if self.hypervelocity_profile
            else 5
        )
        return hyperliquid_price_tick(price, size_decimals=size_decimals)

    def _pending_expired(
        self,
        pending: PendingMakerEntry,
        record: dict[str, Any],
    ) -> bool:
        age = self._hypervelocity_timestamp(record) - pending.submitted_at
        ttl_seconds = (
            self.hypervelocity_profile.entry_ttl_seconds
            if self.hypervelocity_profile is not None
            else HypervelocityContract().entry_ttl_seconds
        )
        return age.total_seconds() > ttl_seconds

    def _usable_book(self, record: dict[str, Any]) -> BookSnapshot | None:
        return self._usable_book_at(self._hypervelocity_timestamp(record))

    def _usable_book_at(self, observed_at: pd.Timestamp) -> BookSnapshot | None:
        """Return a book usable at the exact backend decision timestamp."""
        book = self.book_feed.latest()
        if book is None or book.is_empty():
            return None
        now_ms = observed_at.timestamp() * 1000.0
        age_ms = book.age_ms(now_ms)
        if age_ms < 0.0 or age_ms > self.max_book_age_ms:
            return None
        return book

    def _event_decision_timestamp(self, record: dict[str, Any]) -> pd.Timestamp:
        """Return the later of causal candle close and latest event evidence."""
        bridge = self._event_shadow_bridge
        if bridge is None:
            raise RuntimeError("Hypervelocity event shadow runtime is not attached")
        candle_close = self._hypervelocity_timestamp(record)
        event_time = pd.Timestamp(bridge.controller.port.account_snapshot().observed_at)
        return max(candle_close, event_time)

    def _hypervelocity_timestamp(self, record: dict[str, Any]) -> pd.Timestamp:
        return pd.Timestamp(record["timestamp"]) + pd.Timedelta(minutes=1)

    def _hypervelocity_feed_ts(self, record: dict[str, Any]) -> str:
        return self._hypervelocity_timestamp(record).isoformat()

    def process_frame(self, ohlcv: pd.DataFrame, *, max_bars: int | None = None) -> int:
        """Walk a DataFrame of bars; return count processed in this call."""
        frame = _prepare_ohlcv(ohlcv, max_bars=max_bars)
        n = 0
        for _, row in frame.iterrows():
            self.on_bar(row)
            n += 1
        return n

    def warm_up(self, ohlcv: pd.DataFrame, *, max_bars: int | None = None) -> int:
        """Seed the indicator buffer without simulating historical orders."""
        frame = _prepare_ohlcv(ohlcv, max_bars=max_bars)
        for _, row in frame.iterrows():
            record = _row_to_buffer_record(row)
            _append_bar_record(
                self.buffer_rows,
                record,
                max_lookback=DEFAULT_MAX_LOOKBACK,
            )
            timestamp = record.get("timestamp")
            if isinstance(timestamp, pd.Timestamp):
                self._last_ts = timestamp
        self.bars_processed += len(frame)
        return len(frame)

    def reconcile_downtime(
        self,
        ohlcv: pd.DataFrame,
        *,
        funding_rates: Mapping[pd.Timestamp, float],
    ) -> int:
        """Replay missed HL bars only against state active before restart."""
        if self._shadow_resume is None or not self._is_hypervelocity:
            raise RuntimeError(
                "downtime reconciliation requires resumed Hypervelocity state"
            )
        if isinstance(ohlcv, pd.DataFrame) and ohlcv.empty:
            return 0
        frame = _prepare_ohlcv(ohlcv, max_bars=None)
        cutoff = self._reconciled_through or _resume_timestamp(
            self._shadow_resume.state_asof
        )
        missed = _bars_closing_after(
            frame, cutoff=cutoff, timeframe=self.loadout.timeframe
        )
        if missed.empty:
            return 0
        if "source" not in missed or not missed["source"].eq("hl").all():
            raise RuntimeError("downtime reconciliation requires Hyperliquid bars")
        rates = _normalized_funding_rates(funding_rates)
        self._validate_reconciliation_funding(missed, rates)
        self.ensure_session_identity()
        for _, row in missed.iterrows():
            self._reconcile_downtime_bar(row, rates)
        final_record = _row_to_buffer_record(missed.iloc[-1])
        self._reconciled_through = _bar_close_timestamp(
            final_record, timeframe=self.loadout.timeframe
        )
        return len(missed)

    def reconcile_event_downtime_funding(
        self,
        ohlcv: pd.DataFrame,
        *,
        funding_rates: Mapping[pd.Timestamp, float],
    ) -> int:
        """Reconcile only missed funding; candles have no fill authority."""
        if not self.event_downtime_funding_enabled or self._shadow_resume is None:
            raise RuntimeError("event funding reconciliation requires an open resume")
        if isinstance(ohlcv, pd.DataFrame) and ohlcv.empty:
            return 0
        frame = _prepare_ohlcv(ohlcv, max_bars=None)
        cutoff = _resume_timestamp(self._shadow_resume.state_asof)
        missed = _bars_closing_after(
            frame,
            cutoff=cutoff,
            timeframe=self.loadout.timeframe,
        )
        if missed.empty:
            return 0
        if "source" not in missed or not missed["source"].eq("hl").all():
            raise RuntimeError("event funding reconciliation requires Hyperliquid bars")
        rates = _normalized_funding_rates(funding_rates)
        self._validate_reconciliation_funding(missed, rates)
        self.ensure_session_identity()
        for _, row in missed.iterrows():
            self._reconcile_event_funding_bar(row, rates)
        self._reconciled_through = _bar_close_timestamp(
            _row_to_buffer_record(missed.iloc[-1]),
            timeframe=self.loadout.timeframe,
        )
        return len(missed)

    def _reconcile_event_funding_bar(
        self,
        row: pd.Series,
        rates: Mapping[pd.Timestamp, float],
    ) -> None:
        record = _row_to_buffer_record(row)
        _append_bar_record(self.buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK)
        self.bars_processed += 1
        self._last_ts = pd.Timestamp(record["timestamp"])
        closed_at = _bar_close_timestamp(record, timeframe=self.loadout.timeframe)
        if not _is_funding_boundary(record, timeframe=self.loadout.timeframe):
            return
        bridge = self._event_shadow_bridge
        if bridge is None or closed_at not in rates:
            raise RuntimeError("event funding reconciliation state is incomplete")
        bridge.apply_funding(
            hourly_rate=rates[closed_at],
            oracle_price=float(record["close"]),
            applied_at=closed_at.isoformat(),
        )

    def _validate_reconciliation_funding(
        self,
        frame: pd.DataFrame,
        rates: Mapping[pd.Timestamp, float],
    ) -> None:
        if self.engine.position.qty == 0.0 and self._pending_maker_entry is None:
            return
        for _, row in frame.iterrows():
            record = _row_to_buffer_record(row)
            if _is_funding_boundary(record, timeframe=self.loadout.timeframe):
                closed_at = _bar_close_timestamp(
                    record, timeframe=self.loadout.timeframe
                )
                if closed_at not in rates:
                    raise RuntimeError(
                        f"missing Hyperliquid funding history at {closed_at.isoformat()}"
                    )

    def _reconcile_downtime_bar(
        self,
        row: pd.Series,
        rates: Mapping[pd.Timestamp, float],
    ) -> None:
        record = _row_to_buffer_record(row)
        _append_bar_record(self.buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK)
        self.bars_processed += 1
        self._last_ts = pd.Timestamp(record["timestamp"])
        self._process_hypervelocity_reconciliation(record)
        closed_at = _bar_close_timestamp(record, timeframe=self.loadout.timeframe)
        if self.engine.position.qty != 0.0 and closed_at in rates:
            self.engine.apply_funding(
                feed_ts=closed_at.isoformat(),
                oracle_px=float(record["close"]),
                funding_rate_hourly=rates[closed_at],
            )

    def _process_hypervelocity_reconciliation(
        self, record: dict[str, Any]
    ) -> str | None:
        """Manage an existing target/order without creating offline entries."""
        book = self._usable_book(record)
        if self.engine.position.qty != 0.0:
            return self._fill_hypervelocity_target(record, book)
        pending = self._pending_maker_entry
        if pending is None:
            return None
        direction = self._desired_hypervelocity_direction()
        self._observe_entry_direction(direction)
        if pending.direction != direction:
            self._cancel_pending(record, "regime_changed_during_downtime")
        elif self._pending_expired(pending, record):
            self._expire_pending(record, "entry_ttl_expired_during_downtime")
        elif entry_was_filled(
            pending,
            record,
            book=book,
            tick_size=self._hypervelocity_tick(pending.limit_price),
        ):
            return self._fill_pending_entry(record, book)
        return None

    def ensure_session_identity(self) -> None:
        """Write exactly one session_start row for this backend run.

        Stamps the session ``execution_mode`` (shadow|paper) plus dry-run
        honesty fields so ledger mode never silently defaults to paper when
        the daemon is shadow.
        """
        if self._identity_written:
            return
        from hypervector.paper.order_intent import NETWORK_MAINNET

        position = self.engine.position
        resume = self._shadow_resume
        append_paper_decision(
            self.root,
            {
                "feed_ts": "session_start",
                "run_id": self.run_id,
                "export_id": str(self.export_id),
                "strategy_name": self.strategy_name,
                "symbol": self.loadout.symbol,
                "timeframe": self.loadout.timeframe,
                "data_root": str(self.root.resolve()),
                "action": "session_start",
                "execution_model": (
                    self.hypervelocity_profile.shadow_execution_model
                    if self.hypervelocity_profile is not None
                    else "legacy_bar_through_v1"
                ),
                "execution_data_source": (
                    "hyperliquid_public_ws_l2_trades_active_asset_ctx"
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "execution_evidence_fresh": False,
                "execution_submit_latency_ms": (
                    self.hypervelocity_profile.execution_submit_latency_ms
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "execution_cancel_latency_ms": (
                    self.hypervelocity_profile.execution_cancel_latency_ms
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "execution_update_latency_ms": (
                    self.hypervelocity_profile.execution_update_latency_ms
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "execution_queue_ahead_qty": None,
                "execution_requested_qty": None,
                "cumulative_filled_qty": None,
                "remaining_qty": None,
                "liquidity_side": None,
                "margin_model": (
                    "hyperliquid_isolated_v1"
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "liquidation_execution_model": (
                    LIQUIDATION_EXECUTION_MODEL
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "partial_liquidation_supported": (
                    PARTIAL_LIQUIDATION_SUPPORTED
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "backstop_liquidation_supported": (
                    self.hypervelocity_profile.backstop_liquidation_supported
                    if self.hypervelocity_profile is not None
                    else None
                ),
                "conviction": self.conviction,
                "metalabel_mode": self.metalabel_mode,
                "metalabel_bundle_id": self.conviction_provider.bundle_id,
                "strategy_params": {
                    "strategy": (
                        self.hypervelocity_profile.strategy_id
                        if self.hypervelocity_profile
                        else self.loadout.strategy_name
                    ),
                    **_effective_strategy_params(self.loadout),
                },
                "position_policy": (
                    self.hypervelocity_profile.position_policy()
                    if self.hypervelocity_profile
                    else None
                ),
                "regime_policy": (
                    self.hypervelocity_profile.regime_policy()
                    if self.hypervelocity_profile
                    else None
                ),
                "portfolio_spec": self._portfolio_spec,
                "portfolio_fingerprint": self._portfolio_fingerprint,
                "portfolio_profile_changed_from": (
                    resume.portfolio_profile_changed_from
                    if resume is not None
                    else None
                ),
                "exits": _effective_exits(self.loadout),
                "risk": _effective_risk(self.loadout),
                "execution": _effective_execution(
                    self.loadout, profile=self.hypervelocity_profile
                ),
                "costs": self._effective_costs(),
                "runtime": {
                    "lookback_days": self.lookback_days,
                    "live_activated_at": (
                        self._live_activated_at.isoformat()
                        if self._live_activated_at is not None
                        else None
                    ),
                },
                "orderbook_archive": (
                    {
                        "enabled": self.hypervelocity_profile.orderbook_archive_enabled,
                        "depth_levels": (
                            self.hypervelocity_profile.orderbook_archive_depth_levels
                        ),
                        "path_pattern": (
                            "cache/events/hyperliquid/<SYMBOL>/<UTC_DAY>/"
                            "{l2.parquet,trades.parquet,asset_context.parquet,gaps.jsonl}"
                        ),
                    }
                    if self.hypervelocity_profile is not None
                    else {"enabled": False}
                ),
                "bars_processed": self.bars_processed,
                "execution_mode": self.execution_mode,
                "submitted": False,
                "network": NETWORK_MAINNET,
                "position_qty": float(position.qty),
                "position_avg_px": float(position.avg_px),
                "liquidation_price": self._current_liquidation_price(),
                "realized_pnl": float(position.realized_pnl),
                "unrealized_pnl": (
                    float(resume.unrealized_pnl) if resume is not None else 0.0
                ),
                "equity": (
                    float(resume.equity) if resume is not None else float(self.equity)
                ),
                "init_cash": float(self.engine.initial_cash),
                "resumed_shadow_portfolio": resume is not None,
                "portfolio_state_asof": (
                    resume.state_asof if resume is not None else None
                ),
                "no_submit": True,
            },
        )
        self._identity_written = True

    def _effective_costs(self) -> dict[str, object]:
        if self.hypervelocity_profile is None:
            return dict(self.loadout.costs or {})
        snapshot = self.cost_provider.snapshot()
        return {
            "fee_tier": snapshot.fee_tier,
            "maker_fee_rate": snapshot.maker_fee,
            "taker_fee_rate": snapshot.taker_fee,
            "slippage_bps": snapshot.slippage_bps,
            "funding_source": "live_meta_and_asset_contexts",
            "funding_rate_hourly": snapshot.funding_rate_hourly,
            "funding_oracle_px": snapshot.oracle_px,
            "funding_asof_ts": snapshot.asof_ts,
            "funding_refresh_seconds": self.cost_provider.funding_poll_secs,
            "funding_accrual": "hourly_boundary",
        }

    def result(self) -> PaperSessionResult:
        self.ensure_session_identity()
        return PaperSessionResult(
            run_id=self.run_id,
            decisions_path=self.decisions_path,
            bars_processed=self.bars_processed,
            fills_count=self.fills_count,
            export_dir=self.loadout.export_dir,
        )


def run_paper_session_offline(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    ohlcv: pd.DataFrame,
    conviction: float = 0.5,
    fee_tier: int = 0,
    max_bars: int | None = None,
    funding_rate_hourly: float | None = None,
) -> PaperSessionResult:
    """Walk injected OHLCV bars through loadout alpha into paper fills.

    Warm-up matches :class:`HypervectorStrategy`: no trade when buffer length
    is less than 2. Uses loadout/injected funding rate (no network poll).
    Open positions receive signed funding once per bar. No venue orders.
    """
    session = PaperSession(
        export_dir=export_dir,
        data_root=data_root,
        conviction=conviction,
        fee_tier=fee_tier,
        sandbox_enabled=False,
        funding_rate_hourly=funding_rate_hourly,
        enable_funding_refresh=False,
    )
    session.process_frame(ohlcv, max_bars=max_bars)
    return session.result()


def _prepare_ohlcv(ohlcv: pd.DataFrame, *, max_bars: int | None) -> pd.DataFrame:
    if ohlcv is None or not isinstance(ohlcv, pd.DataFrame) or ohlcv.empty:
        raise ValueError("OHLCV must be a non-empty DataFrame")
    frame = ohlcv.copy()
    if "timestamp" not in frame.columns and frame.index.name == "timestamp":
        frame = frame.reset_index()
    missing = [c for c in _OHLCV_REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    if max_bars is not None:
        frame = frame.iloc[: int(max_bars)]
    return frame.reset_index(drop=True)


def _row_to_buffer_record(row: pd.Series) -> dict[str, Any]:
    ts = row["timestamp"] if "timestamp" in row.index else None
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        ts = pd.Timestamp.utcnow()
    else:
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    return {
        "timestamp": ts,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }


def _buffer_to_df(buffer: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(buffer)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    return df.loc[:, list(_OHLCV_REQUIRED)].astype(float)


def _feed_ts(record: dict[str, Any]) -> str:
    ts = record.get("timestamp")
    if ts is None:
        return "unknown"
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    return str(ts)


def _timeframe_minutes(timeframe: str) -> int:
    values = {"1m": 1, "5m": 5, "15m": 15}
    if timeframe not in values:
        raise ValueError(f"unsupported funding timeframe: {timeframe}")
    return values[timeframe]


def _bar_close_timestamp(
    record: dict[str, Any],
    *,
    timeframe: str,
) -> pd.Timestamp:
    return pd.Timestamp(record["timestamp"]) + pd.Timedelta(
        minutes=_timeframe_minutes(timeframe)
    )


def _is_funding_boundary(
    record: dict[str, Any],
    *,
    timeframe: str,
) -> bool:
    closed_at = _bar_close_timestamp(record, timeframe=timeframe)
    return closed_at.minute == 0 and closed_at.second == 0


def _resume_timestamp(value: str) -> pd.Timestamp:
    """Parse an authoritative ledger timestamp or fail closed."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"invalid shadow portfolio state timestamp: {value!r}"
        ) from exc
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _bars_closing_after(
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    timeframe: str,
) -> pd.DataFrame:
    """Return timestamp-ordered bars whose close follows persisted state."""
    normalized = frame.copy()
    timestamps = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized = normalized.assign(timestamp=timestamps).sort_values("timestamp")
    closes = normalized["timestamp"] + pd.Timedelta(
        minutes=_timeframe_minutes(timeframe)
    )
    return normalized.loc[closes > cutoff].reset_index(drop=True)


def _normalized_funding_rates(
    rates: Mapping[pd.Timestamp, float],
) -> dict[pd.Timestamp, float]:
    """Normalize historical funding keys to exact UTC timestamps."""
    normalized: dict[pd.Timestamp, float] = {}
    for raw_timestamp, raw_rate in rates.items():
        timestamp = pd.Timestamp(raw_timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        rate = float(raw_rate)
        if not math.isfinite(rate):
            raise RuntimeError(f"non-finite funding history at {timestamp.isoformat()}")
        normalized[timestamp] = rate
    return normalized


def _exits_dict(loadout: StrategyLoadout) -> dict[str, Any]:
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    return raw


def _effective_strategy_params(loadout: StrategyLoadout) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.params or {})
    contract = HypervelocityContract()
    return {
        "leverage": contract.leverage,
        "target_margin_pct": contract.target_margin_pct,
    }


def _effective_exits(loadout: StrategyLoadout) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.exits or {})
    contract = HypervelocityContract()
    return {
        "mode": "strategy_target_only",
        "target_margin_pct": contract.target_margin_pct,
        "target_price_fraction": contract.target_price_fraction,
        "target_basis": "gross_margin_return_before_costs",
        "stop": None,
        "range_policy": contract.open_position_range_policy,
    }


def _effective_risk(loadout: StrategyLoadout) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.risk or {})
    contract = HypervelocityContract()
    return {
        "mode": "fixed_margin_fraction",
        "margin_fraction": contract.margin_fraction,
        "notional_fraction": contract.notional_fraction,
    }


def _effective_execution(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None = None,
) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return {"order_type": "market", "time_in_force": "ioc"}
    contract = HypervelocityContract()
    event_model = profile.shadow_execution_model if profile else "legacy_bar_through_v1"
    execution: dict[str, Any] = {
        "order_type": contract.order_type,
        "time_in_force": contract.time_in_force,
        "fill_rule": (
            "public_l2_trade_event_tape"
            if event_model == "nautilus_event_v1"
            else "through_one_tick"
        ),
        "fill_model": (
            event_model if profile is not None else PostOnlyLimitFillModel.fill_model_id
        ),
        "legacy_comparator": "legacy_bar_through_v1",
        "price_tick_mode": "hyperliquid_dynamic",
        "entry_ttl_seconds": (
            profile.entry_ttl_seconds
            if profile is not None
            else contract.entry_ttl_seconds
        ),
        "expired_entry_rearm_policy": (
            profile.expired_entry_rearm_policy
            if profile is not None
            else contract.expired_entry_rearm_policy
        ),
        "same_direction_reentry_policy": (
            profile.same_direction_reentry_policy
            if profile is not None
            else contract.same_direction_reentry_policy
        ),
        "reentry_cooldown_bars": (
            profile.reentry_cooldown_bars if profile is not None else 1
        ),
    }
    if profile is not None:
        execution.update(
            submit_latency_ms=profile.execution_submit_latency_ms,
            cancel_latency_ms=profile.execution_cancel_latency_ms,
            update_latency_ms=profile.execution_update_latency_ms,
            max_event_age_ms=profile.execution_max_event_age_ms,
            restart_queue_policy=profile.restart_queue_policy,
            liquidation_execution_model=profile.liquidation_execution_model,
            partial_liquidation_supported=profile.partial_liquidation_supported,
            partial_liquidation_threshold_usd=(
                profile.partial_liquidation_threshold_usd
            ),
            partial_liquidation_fraction=profile.partial_liquidation_fraction,
            liquidation_cooldown_ms=profile.liquidation_cooldown_ms,
            backstop_liquidation_supported=(profile.backstop_liquidation_supported),
            backstop_maintenance_fraction=profile.backstop_maintenance_fraction,
            backstop_accounting_model=profile.backstop_accounting_model,
        )
    return execution


def _portfolio_spec(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None,
    strategy_name: str,
) -> dict[str, object]:
    return {
        "strategy_name": strategy_name,
        "symbol": loadout.symbol,
        "timeframe": loadout.timeframe,
        "strategy_params": {
            "strategy": profile.strategy_id
            if profile is not None
            else loadout.strategy_name,
            **_effective_strategy_params(loadout),
        },
        "position_policy": profile.position_policy() if profile is not None else None,
        "regime_policy": profile.regime_policy() if profile is not None else None,
        "exits": _effective_exits(loadout),
        "risk": _effective_risk(loadout),
        "execution": _effective_execution(loadout, profile=profile),
    }


def _restore_pending_maker_entry(
    resume: ShadowPortfolioResume | None,
) -> PendingMakerEntry | None:
    """Translate validated ledger state into the runtime maker-order type."""
    pending = resume.pending_entry if resume is not None else None
    if pending is None:
        return None
    return PendingMakerEntry(
        direction=pending.direction,
        qty=pending.qty,
        limit_price=pending.limit_price,
        submitted_at=pd.Timestamp(pending.submitted_at),
        conviction=pending.conviction,
        conviction_source=pending.conviction_source,
        metalabel_p=pending.metalabel_p,
        metalabel_bundle_id=pending.metalabel_bundle_id,
    )


def _target_resume_annotation(
    target: PendingTargetResume,
    inherited: ShadowOrderAnnotation | None,
    default_conviction: float,
) -> ShadowOrderAnnotation:
    """Recover target annotation, falling back only to its parent entry."""
    return ShadowOrderAnnotation(
        conviction=(
            target.conviction
            if target.conviction is not None
            else inherited.conviction
            if inherited is not None
            else default_conviction
        ),
        conviction_source=(
            target.conviction_source
            or (inherited.conviction_source if inherited is not None else "fixed")
        ),
        metalabel_p=(
            target.metalabel_p
            if target.metalabel_p is not None
            else inherited.metalabel_p
            if inherited is not None
            else None
        ),
        metalabel_bundle_id=(
            target.metalabel_bundle_id
            or (inherited.metalabel_bundle_id if inherited is not None else None)
        ),
    )


def _cost_provider_from_loadout(
    loadout: StrategyLoadout,
    *,
    fee_tier: int,
    funding_rate_hourly: float | None = None,
) -> CostProvider:
    costs = loadout.costs or {}
    slippage_bps = float(costs.get("slippage_bps", 2.0))
    if funding_rate_hourly is not None:
        funding_hourly = float(funding_rate_hourly)
    elif costs.get("funding_rate_1h") is not None:
        funding_hourly = float(costs["funding_rate_1h"])
    elif costs.get("funding_rate_hourly") is not None:
        funding_hourly = float(costs["funding_rate_hourly"])
    elif costs.get("funding_rate_8h") is not None:
        funding_hourly = float(costs["funding_rate_8h"]) / 8.0
    else:
        funding_hourly = 0.0
    return CostProvider(
        fee_tier=int(fee_tier),
        slippage_bps=slippage_bps,
        funding_rate_hourly=funding_hourly,
        assume_taker=not is_hypervelocity_strategy(loadout.strategy_name),
    )


def _build_conviction_provider(
    *,
    conviction: float,
    metalabel_enabled: bool,
    metalabeler: Any | None,
    conviction_provider: ConvictionProvider | None,
    data_root: Path | str | None = None,
    metalabel_min_p: float = DEFAULT_METALABEL_MIN_P,
    metalabel_filter: bool = True,
    metalabel_mode: MetalabelMode | None = None,
) -> ConvictionProvider:
    """Fixed by default; metalabel scales and filters when enabled."""
    if conviction_provider is not None:
        return conviction_provider
    mode = resolve_metalabel_mode(
        enabled=metalabel_enabled,
        filter_entries=metalabel_filter,
        requested=metalabel_mode,
    )
    if mode == "off":
        return FixedConvictionProvider(conviction)
    try:
        from hypervector.ml.features import FeatureBuilder
        from hypervector.ml.metalabel import Metalabeler

        ml = (
            metalabeler
            if metalabeler is not None
            else Metalabeler.from_env(data_root=data_root)
        )
        if mode == "observe":
            active_mode = "observe"
        elif mode == "scale":
            active_mode = "scale"
        else:
            active_mode = "filter"
        return MetalabelConvictionProvider(
            ml,
            FeatureBuilder(),
            fixed_fallback=float(conviction),
            min_p=float(metalabel_min_p),
            filter_entries=mode == "filter",
            fail_closed=mode == "filter",
            mode=active_mode,
        )
    except Exception as exc:  # noqa: BLE001 — keep session usable on load failure
        logger.warning(
            "metalabel_enabled but provider setup failed; using fixed conviction: %s",
            exc,
        )
        return FixedConvictionProvider(conviction)


def _build_hypervelocity_directional_provider(
    profile: HypervelocityProfile,
    *,
    conviction: float,
    metalabel_min_p: float,
) -> DirectionalMetalabelConvictionProvider:
    """Load the configured long/short annotation-only model pair."""
    from hypervector.ml.features import FeatureBuilder
    from hypervector.ml.metalabel import Metalabeler

    def provider(bundle: Path) -> MetalabelConvictionProvider:
        model = Metalabeler.from_root(bundle)
        return MetalabelConvictionProvider(
            model,
            FeatureBuilder(),
            fixed_fallback=conviction,
            min_p=metalabel_min_p,
            filter_entries=False,
            fail_closed=False,
            mode="observe",
        )

    return DirectionalMetalabelConvictionProvider(
        long_provider=provider(profile.model_long_bundle),
        short_provider=provider(profile.model_short_bundle),
    )


def _conviction_fill_kwargs(cv: ConvictionResult) -> dict[str, Any]:
    """Fields accepted by ExplicitFillEngine.apply_market_fill."""
    return {
        "conviction": cv.conviction,
        "conviction_source": cv.source,
        "metalabel_p": cv.metalabel_p,
        "metalabel_bundle_id": cv.metalabel_bundle_id,
    }


def _entry_qty(
    *,
    df: pd.DataFrame,
    loadout: StrategyLoadout,
    exits: dict[str, Any],
    equity: float,
    conviction: float,
    mark_px: float,
) -> float | None:
    if mark_px <= 0 or equity <= 0:
        return None
    try:
        stop_frac, _tp = _stop_tp_fracs(df, exits)
    except Exception:
        stop_frac = 0.01
    size_frac = position_size_frac(
        equity,
        stop_frac=max(float(stop_frac), 1e-6),
        loadout=loadout,
        conviction=conviction,
    )
    if size_frac <= 0:
        return None
    notional = equity * float(size_frac)
    qty = notional / mark_px
    return qty if qty > 0 else None
