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
from hypervector.paper.book import BookFeed, BookSnapshot
from hypervector.paper.conviction import (
    ConvictionProvider,
    ConvictionResult,
    FixedConvictionProvider,
    MetalabelConvictionProvider,
)
from hypervector.paper.costs import CostProvider
from hypervector.paper.fill_models import (
    DEFAULT_MAX_BOOK_AGE_MS,
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
)
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.ledger import DECISIONS_FILENAME, append_paper_decision
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
        preferred_fill_model: str = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
        max_book_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS,
        book_feed: BookFeed | None = None,
        enable_book_poll: bool = False,
        metalabel_enabled: bool = False,
        metalabeler: Any | None = None,
        conviction_provider: ConvictionProvider | None = None,
    ) -> None:
        register_all_strategies()
        export_path = Path(export_dir)
        if not export_path.is_dir():
            raise FileNotFoundError(f"export_dir not found: {export_path}")

        self.loadout = load_strategy_loadout(export_path, strict=True)
        self.root = Path(data_root)
        self.paths = ensure_data_layout(self.root)
        self.decisions_path = self.paths.paper_decisions / DECISIONS_FILENAME
        self.conviction = float(conviction)
        self.sandbox_enabled = bool(sandbox_enabled)
        self.enable_funding_refresh = bool(enable_funding_refresh)
        self.enable_book_poll = bool(enable_book_poll)
        self.max_book_age_ms = float(max_book_age_ms)
        self.preferred_fill_model = str(preferred_fill_model)
        self.metalabel_enabled = bool(metalabel_enabled)
        self.conviction_provider = _build_conviction_provider(
            conviction=self.conviction,
            metalabel_enabled=self.metalabel_enabled,
            metalabeler=metalabeler,
            conviction_provider=conviction_provider,
        )

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
        self.engine = ExplicitFillEngine(
            self.root,
            cost_provider=self.cost_provider,
            run_id=self.run_id,
            export_id=str(self.export_id),
            strategy_name=self.loadout.strategy_name,
            symbol=self.loadout.symbol,
            timeframe=self.loadout.timeframe,
            conviction=self.conviction,
            sandbox_enabled=self.sandbox_enabled,
            preferred_fill_model=self.preferred_fill_model,
            max_book_age_ms=self.max_book_age_ms,
        )
        self.equity = (
            float(self.loadout.init_cash)
            if self.loadout.init_cash is not None
            else 10_000.0
        )
        self.exits = _exits_dict(self.loadout)
        self.buffer_rows: list[dict[str, Any]] = []
        self.fills_count = 0
        self.bars_processed = 0
        self._last_ts: pd.Timestamp | None = None
        self._last_funding_refresh_mono: float = 0.0

    def inject_book(self, snap: BookSnapshot) -> None:
        """Inject a BookSnapshot for offline tests (no network)."""
        self.book_feed.update(snap)

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
            logger.warning("funding refresh failed for %s: %s", self.loadout.symbol, exc)
            return None
        self._last_funding_refresh_mono = now
        return rate

    def on_bar(self, row: pd.Series | dict[str, Any]) -> str | None:
        """Process one OHLCV bar. Returns fill action or None.

        When a position is open, applies one hour of signed funding at bar close
        using the current ``cost_provider`` rate (no network in this method).
        """
        record = _row_to_buffer_record(row if isinstance(row, pd.Series) else pd.Series(row))
        _append_bar_record(
            self.buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK
        )
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

        fill_action: str | None = None
        if len(self.buffer_rows) >= 2:
            fill_action = self._process_intent(record)

        # Signed funding once per bar while open (configured/last rate).
        if self.engine.position.qty != 0.0:
            mark_px = float(record["close"])
            self.engine.apply_funding(
                feed_ts=_feed_ts(record),
                oracle_px=mark_px,
            )

        return fill_action

    def _process_intent(self, record: dict[str, Any]) -> str | None:
        """Map strategy intent on the latest bar into a market fill, if any."""
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

        book = self.book_feed.latest()
        # Scale-only conviction per decision (fixed by default; metalabel when enabled).
        cv = self.conviction_provider.resolve(bars=df)
        cv_kwargs = _conviction_fill_kwargs(cv)

        if action == "close":
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
            qty = _entry_qty(
                df=df,
                loadout=self.loadout,
                exits=self.exits,
                equity=self.equity,
                conviction=cv.conviction,
                mark_px=mark_px,
            )
            if qty is None or qty <= 0:
                return None
            side = "buy" if action == "enter_long" else "sell"
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

    def process_frame(
        self, ohlcv: pd.DataFrame, *, max_bars: int | None = None
    ) -> int:
        """Walk a DataFrame of bars; return count processed in this call."""
        frame = _prepare_ohlcv(ohlcv, max_bars=max_bars)
        n = 0
        for _, row in frame.iterrows():
            self.on_bar(row)
            n += 1
        return n

    def ensure_session_identity(self) -> None:
        """Write a session_start row if no decisions exist yet."""
        if not self.decisions_path.is_file():
            append_paper_decision(
                self.root,
                {
                    "feed_ts": "session_start",
                    "run_id": self.run_id,
                    "export_id": str(self.export_id),
                    "strategy_name": self.loadout.strategy_name,
                    "symbol": self.loadout.symbol,
                    "timeframe": self.loadout.timeframe,
                    "action": "session_start",
                    "conviction": self.conviction,
                    "bars_processed": self.bars_processed,
                },
            )

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


def _prepare_ohlcv(
    ohlcv: pd.DataFrame, *, max_bars: int | None
) -> pd.DataFrame:
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


def _exits_dict(loadout: StrategyLoadout) -> dict[str, Any]:
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    return raw


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
    elif "funding_rate_hourly" in costs:
        funding_hourly = float(costs["funding_rate_hourly"])
    elif "funding_rate_8h" in costs:
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
) -> ConvictionProvider:
    """Fixed by default; metalabel only when explicitly enabled (SRS_HV4A_ORDER)."""
    if conviction_provider is not None:
        return conviction_provider
    if not metalabel_enabled:
        return FixedConvictionProvider(conviction)
    try:
        from hypervector.ml.features import FeatureBuilder
        from hypervector.ml.metalabel import Metalabeler

        ml = metalabeler if metalabeler is not None else Metalabeler.from_env()
        return MetalabelConvictionProvider(
            ml,
            FeatureBuilder(),
            fixed_fallback=float(conviction),
        )
    except Exception as exc:  # noqa: BLE001 — keep session usable on load failure
        logger.warning(
            "metalabel_enabled but provider setup failed; using fixed conviction: %s",
            exc,
        )
        return FixedConvictionProvider(conviction)


def _conviction_fill_kwargs(cv: ConvictionResult) -> dict[str, Any]:
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
