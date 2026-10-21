"""Paper session: loadout → bar walk → intent → ExplicitFillEngine.

Offline multi-bar walk and incremental ``on_bar`` for the live daemon share
the same alpha path. No Nautilus node, no venue orders. Funding uses the
configured/last hourly rate offline; optional live refresh is opt-in.

Execution follows the strategy's declared
:class:`~hypervector.strategies.registry.ExecutionProfile`: market fills by
default; with ``post_only_entries`` an entry rests as a post-only limit at the
same-side touch until it fills through its limit, its time-to-live expires or
the strategy's intent changes.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.nautilus.actor import (
    DEFAULT_MAX_LOOKBACK,
    _action_from_intent,
    _append_bar_record,
    _stop_tp_fracs,
)
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.signals import SignalIntent, last_bar_intent
from hypervector.nautilus.sizing import position_size_frac
from hypervector.nautilus.venue_spec import resolve_venue_spec
from hypervector.paper.book import (
    DEFAULT_MAX_BOOK_AGE_MS,
    BookFeed,
    BookSnapshot,
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
    FixedConvictionProvider,
    MetalabelConvictionProvider,
    MetalabelMode,
    resolve_metalabel_mode,
)
from hypervector.paper.costs import CostProvider
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.ledger import (
    DECISIONS_FILENAME,
    append_paper_decision,
    ensure_paper_layout,
)
from hypervector.paper.maker_execution import (
    PendingMakerEntry,
    PostOnlyLimitFillModel,
    entry_limit_price,
    entry_was_filled,
    hyperliquid_price_tick,
    quantize_size_down,
)

# Re-exported (``name as name``) for hypervector.live.session and tests.
from hypervector.paper.session_bars import (
    _bar_close_timestamp as _bar_close_timestamp,
    _buffer_to_df as _buffer_to_df,
    _feed_ts as _feed_ts,
    _is_funding_boundary as _is_funding_boundary,
    _prepare_ohlcv as _prepare_ohlcv,
    _row_to_buffer_record as _row_to_buffer_record,
    _timeframe_minutes as _timeframe_minutes,
)
from hypervector.paper.session_configuration import (
    _exits_dict as _exits_dict,
    _portfolio_spec as _portfolio_spec,
    portfolio_fingerprint,
)
from hypervector.paper.session_identity import session_identity_payload
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import ExecutionProfile, execution_profile

logger = logging.getLogger(__name__)


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
        lookback_days: int | None = None,
        initial_cash_usd: float | None = None,
    ) -> None:
        register_all_strategies()
        export_path = Path(export_dir)
        if not export_path.is_dir():
            raise FileNotFoundError(f"export_dir not found: {export_path}")

        self.loadout = load_strategy_loadout(export_path, strict=True)
        # Fail on an unsupported candle duration before any IO, not on the
        # first bar that holds a position (funding boundaries need it).
        _timeframe_minutes(self.loadout.timeframe)
        requested_initial_cash = _validated_initial_cash(initial_cash_usd)
        self.execution: ExecutionProfile = execution_profile(self.loadout.strategy_name)
        # Post-only entries rest at the touch, so they need the venue's size
        # precision (price tick, size quantum) before any bar is processed.
        self._size_decimals = (
            resolve_venue_spec(self.loadout.symbol, self.loadout.meta).size_decimals
            if self.execution.post_only_entries
            else None
        )
        self.lookback_days = lookback_days
        self.root = Path(data_root)
        self.paths = ensure_paper_layout(self.root)
        self.decisions_path = self.paths.paper_decisions / DECISIONS_FILENAME
        self.conviction = float(conviction)
        self.sandbox_enabled = bool(sandbox_enabled)
        self.enable_funding_refresh = bool(enable_funding_refresh)
        self.enable_book_poll = bool(enable_book_poll)
        # The taker book gate decides whether a market entry fires; a resting
        # post-only entry does not cross the spread, so it is not gated.
        self.book_gate_enabled = (
            bool(book_gate_enabled) and not self.execution.post_only_entries
        )
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
        # Fixed sizing is never scaled or filtered by a model: models annotate.
        if self.execution.fixed_sizing and self.metalabel_mode in ("scale", "filter"):
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

        self.strategy_name = self.loadout.strategy_name
        self._portfolio_spec = _portfolio_spec(
            self.loadout,
            strategy_name=self.strategy_name,
        )
        self._portfolio_fingerprint = portfolio_fingerprint(self._portfolio_spec)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.export_id = self.loadout.run_id or export_path.name
        self.cost_provider = _cost_provider_from_loadout(
            self.loadout,
            fee_tier=fee_tier,
            funding_rate_hourly=funding_rate_hourly,
        )
        self.book_feed = (
            book_feed
            if book_feed is not None
            else BookFeed(self.loadout.symbol, max_age_ms=self.max_book_age_ms)
        )
        self.equity = (
            requested_initial_cash
            if requested_initial_cash is not None
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
        self.exits = _exits_dict(self.loadout)
        self.buffer_rows: list[dict[str, Any]] = []
        self.fills_count = 0
        self.bars_processed = 0
        self._last_ts: pd.Timestamp | None = None
        self._last_funding_refresh_mono: float = 0.0
        self._identity_written = False
        self._pending_maker_entry: PendingMakerEntry | None = None
        self._live_activated_at: pd.Timestamp | None = None

    @property
    def pending_maker_entry(self) -> PendingMakerEntry | None:
        """Return the resting post-only entry, if any."""
        return self._pending_maker_entry

    def inject_book(self, snap: BookSnapshot) -> None:
        """Inject a BookSnapshot for offline tests (no network)."""
        self.book_feed.update(snap)

    def mark_live(self, *, activated_at: pd.Timestamp | None = None) -> None:
        """Record when the session moved from historical warm-up to live bars."""
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

    def refresh_book(self) -> BookSnapshot | None:
        """Poll L2 once when live book polling is enabled."""
        if not self.enable_book_poll:
            return None
        return self.book_feed.poll()

    def on_bar(self, row: pd.Series | dict[str, Any]) -> str | None:
        """Process one OHLCV bar. Returns fill action or None.

        When a position is open and the bar closes on an hourly Hyperliquid
        settlement boundary, applies one hour of signed funding using the
        current ``cost_provider`` rate (no network in this method).
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
        return self._process_bar(record)

    def _process_bar(self, record: dict[str, Any]) -> str | None:
        """Run funding refresh, intent and hourly funding for the buffered bar."""
        self.maybe_refresh_funding()
        fill_action: str | None = None
        if len(self.buffer_rows) >= 2:
            fill_action = self._process_intent(record)
        self._apply_hourly_funding(record)
        return fill_action

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
        self.engine.apply_funding(
            feed_ts=applied_at,
            oracle_px=oracle_px,
            hours=1.0,
        )

    def _process_intent(self, record: dict[str, Any]) -> str | None:
        """Map strategy intent on the latest bar into a fill, if any."""
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

        if is_flat and self._pending_maker_entry is not None:
            filled = self._advance_pending_entry(record, intent)
            if filled is not None or self._pending_maker_entry is not None:
                return filled

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
                now_ms = time.time() * 1000.0
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
            if self.execution.post_only_entries:
                direction = "long" if action == "enter_long" else "short"
                self._submit_pending_entry(record, direction, qty, book, cv)
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

    # --- declared post-only entries --------------------------------------------

    def _advance_pending_entry(
        self, record: dict[str, Any], intent: SignalIntent
    ) -> str | None:
        """Cancel, expire or fill the resting entry against this completed bar.

        The entry is cancelled when the strategy exits or turns to the other
        side, expires after its time-to-live, and otherwise fills at its limit
        only on one-tick-through evidence (book first, else the bar range).
        """
        pending = self._pending_maker_entry
        if pending is None:
            return None
        turned = intent.enter and intent.direction in ("long", "short") and (
            intent.direction != pending.direction
        )
        if intent.exit or turned:
            self._cancel_pending(record, "strategy_intent_changed")
            return None
        closed_at = _bar_close_timestamp(record, timeframe=self.loadout.timeframe)
        age = (closed_at - pending.submitted_at).total_seconds()
        if age > float(self.execution.entry_ttl_seconds):
            self._cancel_pending(record, "entry_ttl_expired")
            return None
        book = self._usable_book_at(closed_at)
        if not entry_was_filled(
            pending,
            record,
            book=book,
            tick_size=self._price_tick(pending.limit_price),
        ):
            return None
        return self._fill_pending_entry(record, book)

    def _submit_pending_entry(
        self,
        record: dict[str, Any],
        direction: str,
        qty: float,
        book: BookSnapshot | None,
        cv: ConvictionResult,
    ) -> None:
        quantity = quantize_size_down(qty, size_decimals=self._venue_size_decimals())
        if quantity <= 0.0:
            return
        closed_at = _bar_close_timestamp(record, timeframe=self.loadout.timeframe)
        del book  # the touch must be fresh at the bar close, not merely latest
        limit = entry_limit_price(
            direction,  # type: ignore[arg-type]
            record,
            book=self._usable_book_at(closed_at),
        )
        self._pending_maker_entry = PendingMakerEntry(
            direction=direction,  # type: ignore[arg-type]
            qty=quantity,
            limit_price=limit,
            submitted_at=closed_at,
            conviction=cv.conviction,
            conviction_source=cv.source,
            metalabel_p=cv.metalabel_p,
            metalabel_bundle_id=cv.metalabel_bundle_id,
        )
        self.engine.record_order_event(
            feed_ts=_feed_ts(record),
            action="submit_entry",
            side="buy" if direction == "long" else "sell",
            qty=quantity,
            limit_px=limit,
            status="pending",
            **_conviction_fill_kwargs(cv),
        )

    def _fill_pending_entry(
        self, record: dict[str, Any], book: BookSnapshot | None
    ) -> str | None:
        pending = self._pending_maker_entry
        if pending is None:
            return None
        maker_fee = self.cost_provider.snapshot().maker_fee
        rec = self.engine.apply_market_fill(
            feed_ts=_feed_ts(record),
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
            fee_override_usd=abs(pending.qty) * pending.limit_price * maker_fee,
        )
        if rec.get("skipped"):
            return None
        self._pending_maker_entry = None
        self.fills_count += 1
        return pending.action

    def _cancel_pending(self, record: dict[str, Any], reason: str) -> None:
        pending = self._pending_maker_entry
        if pending is None:
            return
        self.engine.record_order_event(
            feed_ts=_feed_ts(record),
            action="cancel_entry",
            side=pending.side,
            qty=pending.qty,
            limit_px=pending.limit_price,
            status="canceled",
            reason=reason,
        )
        self._pending_maker_entry = None

    def _venue_size_decimals(self) -> int:
        if self._size_decimals is None:
            raise RuntimeError("post-only entries require resolved venue precision")
        return int(self._size_decimals)

    def _price_tick(self, price: float) -> float:
        return hyperliquid_price_tick(price, size_decimals=self._venue_size_decimals())

    def _usable_book_at(self, observed_at: pd.Timestamp) -> BookSnapshot | None:
        """Return a book usable at the exact decision timestamp."""
        book = self.book_feed.latest()
        if book is None or book.is_empty():
            return None
        now_ms = observed_at.timestamp() * 1000.0
        age_ms = book.age_ms(now_ms)
        if age_ms < 0.0 or age_ms > self.max_book_age_ms:
            return None
        return book

    # --- bar walks -----------------------------------------------------------

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
        """Write exactly one unchanged no-submit identity for this backend run."""
        if self._identity_written:
            return
        append_paper_decision(self.root, session_identity_payload(self))
        self._identity_written = True

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
    Open positions receive one hour of signed funding on each bar that closes
    on an hourly settlement boundary. No venue orders.
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


def _validated_initial_cash(value: float | None) -> float | None:
    if value is None:
        return None
    initial_cash = float(value)
    if not math.isfinite(initial_cash) or initial_cash <= 0.0:
        raise ValueError("initial_cash_usd must be finite and positive")
    return initial_cash


def _cost_provider_from_loadout(
    loadout: StrategyLoadout,
    *,
    fee_tier: int,
    funding_rate_hourly: float | None = None,
) -> CostProvider:
    """Taker fees, configured slippage and the bundle's (or injected) funding.

    Resting post-only fills pass their maker fee explicitly.
    """
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
