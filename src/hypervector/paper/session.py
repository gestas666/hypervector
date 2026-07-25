"""Paper session: loadout → bar walk → intent → ExplicitFillEngine.

Offline multi-bar walk and incremental ``on_bar`` for the live daemon share
the same alpha path. No Nautilus node, no venue orders. Funding uses the
configured/last hourly rate offline; optional live refresh is opt-in.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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
from hypervector.paper.book import BookFeed, BookSnapshot, DEFAULT_MAX_BOOK_AGE_MS
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
    FixedConvictionProvider,
    MetalabelConvictionProvider,
    MetalabelMode,
    resolve_metalabel_mode,
)
from hypervector.paper.costs import CostProvider
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.ledger import DECISIONS_FILENAME, append_paper_decision
from hypervector.paper.maker_execution import (
    DEFAULT_ENTRY_TTL_SECONDS,
    PostOnlyLimitFillModel,
    PendingMakerEntry,
    entry_limit_price,
    entry_was_filled,
    hyperliquid_price_tick,
    quantize_size_down,
    round_price_to_tick,
    target_was_filled,
)
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
    ) -> None:
        register_all_strategies()
        export_path = Path(export_dir)
        if not export_path.is_dir():
            raise FileNotFoundError(f"export_dir not found: {export_path}")

        self.loadout = load_strategy_loadout(export_path, strict=True)
        self._is_hypervelocity = is_hypervelocity_strategy(self.loadout.strategy_name)
        self.hypervelocity_profile = hypervelocity_profile
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
        self.metalabel_mode = resolve_metalabel_mode(
            enabled=bool(metalabel_enabled),
            filter_entries=bool(metalabel_filter),
            requested=metalabel_mode,
        )
        if self._is_hypervelocity and self.metalabel_mode in ("scale", "filter"):
            self.metalabel_mode = "observe"
        self.metalabel_enabled = self.metalabel_mode != "off"
        self.metalabel_min_p = float(metalabel_min_p)
        self.metalabel_filter = self.metalabel_mode == "filter"
        self.execution_mode = str(execution_mode)
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

        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.export_id = self.loadout.run_id or export_path.name
        self.cost_provider = _cost_provider_from_loadout(
            self.loadout,
            fee_tier=(hypervelocity_profile.fee_tier if hypervelocity_profile else fee_tier),
            funding_rate_hourly=funding_rate_hourly,
        )
        if hypervelocity_profile is not None:
            self.cost_provider.slippage_bps = hypervelocity_profile.slippage_bps
            self.cost_provider.funding_poll_secs = hypervelocity_profile.funding_refresh_seconds
        self.book_feed = (
            book_feed
            if book_feed is not None
            else BookFeed(self.loadout.symbol, max_age_ms=self.max_book_age_ms)
        )
        self.equity = (
            float(self.loadout.init_cash)
            if self.loadout.init_cash is not None
            else 10_000.0
        )
        self.strategy_name = (
            hypervelocity_profile.strategy_id
            if hypervelocity_profile is not None
            else self.loadout.strategy_name
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
        self.exits = _exits_dict(self.loadout)
        self.buffer_rows: list[dict[str, Any]] = []
        self.fills_count = 0
        self.bars_processed = 0
        self._last_ts: pd.Timestamp | None = None
        self._last_funding_refresh_mono: float = 0.0
        self._identity_written = False
        self._pending_maker_entry: PendingMakerEntry | None = None
        self._live_telemetry_enabled = False

    @property
    def pending_maker_entry(self) -> PendingMakerEntry | None:
        """Return the current backend-owned pending maker entry, if any."""
        return self._pending_maker_entry

    def inject_book(self, snap: BookSnapshot) -> None:
        """Inject a BookSnapshot for offline tests (no network)."""
        self.book_feed.update(snap)

    def enable_live_telemetry(self) -> None:
        """Enable report-only per-bar telemetry after historical warm-up."""
        self._live_telemetry_enabled = True

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
        if self.enable_book_poll:
            try:
                self.book_feed.poll()
            except Exception as exc:  # noqa: BLE001 — never abort bar path
                logger.warning("book poll failed for %s: %s", self.loadout.symbol, exc)

        if self._is_hypervelocity and self._live_telemetry_enabled:
            self._record_hypervelocity_regime(record)

        fill_action: str | None = None
        if len(self.buffer_rows) >= 2:
            fill_action = self._process_intent(record)

        # Hyperliquid funding settles hourly, not continuously between boundaries.
        if self.engine.position.qty != 0.0 and _is_funding_boundary(
            record,
            timeframe=self.loadout.timeframe,
        ):
            snapshot = self.cost_provider.snapshot()
            oracle_px = snapshot.oracle_px or float(record["close"])
            self.engine.apply_funding(
                feed_ts=_bar_close_timestamp(
                    record,
                    timeframe=self.loadout.timeframe,
                ).isoformat(),
                oracle_px=oracle_px,
                hours=1.0,
            )

        return fill_action

    def _record_hypervelocity_regime(self, record: dict[str, Any]) -> None:
        """Append the causal regime state used by the live entry decision."""
        frame = _buffer_to_df(self.buffer_rows)
        if self.hypervelocity_profile is None:
            direction = self._hypervelocity_direction()
            legacy = current_hypervelocity_regime(frame, direction=direction)
            primary = legacy.primary_regime
            breakout = legacy.breakout_direction
            entry_direction: str | None = legacy.direction
            entry_allowed = legacy.entry_allowed
        else:
            market = current_hypervelocity_market(
                frame,
                regime_config=self.hypervelocity_profile.regime_config,
            )
            primary = market.primary_regime
            breakout = market.breakout_direction
            entry_direction = market.entry_direction
            entry_allowed = market.entry_direction is not None
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
                "primary_regime": primary,
                "breakout_direction": breakout,
                "entry_direction": entry_direction,
                "entry_allowed": entry_allowed,
                "execution_mode": self.execution_mode,
                "submitted": False,
                "place_attempted": False,
                "position_qty": float(self.engine.position.qty),
                "mark_px": float(record["close"]),
            },
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
        book = self._usable_book(record)
        if self.engine.position.qty != 0.0:
            return self._fill_hypervelocity_target(record, book)
        direction = self._desired_hypervelocity_direction()
        allowed = direction is not None
        pending = self._pending_maker_entry
        if pending is not None and self._pending_expired(pending, record):
            self._cancel_pending(record, "entry_ttl_expired")
        elif pending is not None and pending.direction != direction:
            self._cancel_pending(record, "canonical_regime_direction_changed")
        elif pending is not None and entry_was_filled(
            pending,
            record,
            book=book,
            tick_size=self._hypervelocity_tick(pending.limit_price),
        ):
            return self._fill_pending_entry(record, book)
        if self._pending_maker_entry is None and allowed and direction is not None:
            self._submit_pending_entry(record, direction, book)
        return None

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
        )
        if rec.get("skipped"):
            return None
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
        cv = self.conviction_provider.resolve(bars=df)
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
        return age.total_seconds() > DEFAULT_ENTRY_TTL_SECONDS

    def _usable_book(self, record: dict[str, Any]) -> BookSnapshot | None:
        book = self.book_feed.latest()
        if book is None or book.is_empty():
            return None
        now_ms = self._hypervelocity_timestamp(record).timestamp() * 1000.0
        age_ms = book.age_ms(now_ms)
        if age_ms < 0.0 or age_ms > self.max_book_age_ms:
            return None
        return book

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

    def ensure_session_identity(self) -> None:
        """Write exactly one session_start row for this backend run.

        Stamps the session ``execution_mode`` (shadow|paper) plus dry-run
        honesty fields so ledger mode never silently defaults to paper when
        the daemon is shadow.
        """
        if self._identity_written:
            return
        from hypervector.paper.order_intent import NETWORK_MAINNET

        append_paper_decision(
            self.root,
            {
                "feed_ts": "session_start",
                "run_id": self.run_id,
                "export_id": str(self.export_id),
                "strategy_name": self.strategy_name,
                "symbol": self.loadout.symbol,
                "timeframe": self.loadout.timeframe,
                "action": "session_start",
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
                "exits": _effective_exits(self.loadout),
                "risk": _effective_risk(self.loadout),
                "execution": _effective_execution(self.loadout),
                "costs": self._effective_costs(),
                "bars_processed": self.bars_processed,
                "execution_mode": self.execution_mode,
                "submitted": False,
                "network": NETWORK_MAINNET,
                "position_qty": 0.0,
                "position_avg_px": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "equity": float(self.equity),
                "init_cash": float(self.equity),
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


def _effective_execution(loadout: StrategyLoadout) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return {"order_type": "market", "time_in_force": "ioc"}
    contract = HypervelocityContract()
    return {
        "order_type": contract.order_type,
        "time_in_force": contract.time_in_force,
        "fill_rule": "through_one_tick",
        "fill_model": PostOnlyLimitFillModel.fill_model_id,
        "price_tick_mode": "hyperliquid_dynamic",
        "entry_ttl_seconds": DEFAULT_ENTRY_TTL_SECONDS,
    }


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
