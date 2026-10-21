"""Paper daemon lifecycle: warm-up → live bar feed → graceful stop.

Runner owns start/stop only. Bar processing is :class:`PaperSession`.
Feed is :mod:`hypervector.paper.live_node` (REST poll fallback; no venue orders).
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from hypervector.config import DEFAULT_LOOKBACK, FLOOR_LOOKBACK
from hypervector.data.pipeline import load_research_history
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.fill_models import (
    DEFAULT_MAX_BOOK_AGE_MS,
    FILL_MODEL_L2_WALK_V1,
)
from hypervector.paper.live_node import (
    DEFAULT_POLL_INTERVAL_SECS,
    completed_bars_at,
    make_rest_poll_fn,
    partition_live_bars,
)
from hypervector.paper.session import PaperSession
from hypervector.paper.warmup import WarmTailFetcher, refresh_warm_history

logger = logging.getLogger(__name__)

PAPER_BANNER = "PAPER MODE — no venue orders"
SHADOW_BANNER = "SHADOW MODE — no venue orders"


def banner_for_mode(execution_mode: str) -> str:
    """Stderr banner for daemon mode. Shadow is the 4b default; both refuse venue orders."""
    mode = str(execution_mode).lower().strip()
    if mode == "shadow":
        return SHADOW_BANNER
    return PAPER_BANNER


@dataclass(frozen=True)
class PaperDaemonResult:
    """Summary after paper daemon stops."""

    run_id: str
    decisions_path: Path
    export_dir: Path
    warm_bars: int
    live_bars: int
    bars_processed: int
    fills_count: int
    stop_reason: str
    execution_mode: str = "paper"
    warmup_provenance: dict[str, Any] | None = None


def _load_warm_history(
    root: Path,
    *,
    symbol: str,
    timeframe: str,
    lookback_days: int,
    strict_hl_only: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Cache-first warm-up history that a failed research refresh cannot block.

    Warm-up needs only Hyperliquid candles, and :func:`refresh_warm_history`
    tops the tail up from HL afterwards (fail-closed). So when refreshing the
    research window fails (for example a Binance or Bybit outage during the CEX
    backfill), the fresher of the cached window and the HL-only window the
    failed load just kept is served as is. With no cached window the failure
    stands.
    """
    try:
        return load_research_history(
            root,
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            strict_hl_only=strict_hl_only,
        )
    except (RuntimeError, OSError) as exc:  # a failed refresh (network, backfill)
        cached = _cached_warm_history(
            root,
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            strict_hl_only=strict_hl_only,
        )
        if cached is None:
            raise
        frame, provenance = cached
        logger.warning(
            "warm-up history refresh failed (%s: %s); warming up from cached "
            "window %s and the Hyperliquid tail",
            type(exc).__name__,
            exc,
            provenance.get("cache_key"),
        )
        return frame, {**provenance, "refresh_error": f"{type(exc).__name__}: {exc}"}


def _cached_warm_history(
    root: Path,
    *,
    symbol: str,
    timeframe: str,
    lookback_days: int,
    strict_hl_only: bool,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """The freshest cached window: the request's own or the HL-only one (offline).

    Both are read pinned (``max_cache_age=None``). The HL-only entry is the one
    a failed backfill keeps, so it is usually the newest; a tie keeps the
    request's own window.
    """
    best: tuple[pd.Timestamp, pd.DataFrame, dict[str, Any]] | None = None
    for strict in dict.fromkeys((strict_hl_only, True)):
        try:
            frame, provenance = load_research_history(
                root,
                symbol=symbol,
                timeframe=timeframe,
                lookback_days=lookback_days,
                strict_hl_only=strict,
                allow_network=False,
                max_cache_age=None,
            )
        except Exception:  # noqa: BLE001 - a missing or unreadable entry is skipped
            continue
        if not len(frame):
            continue
        end = pd.to_datetime(frame["timestamp"], utc=True).max()
        if best is None or end > best[0]:
            best = (end, frame, provenance)
    return None if best is None else (best[1], best[2])


def start_paper_daemon(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    conviction: float = 0.5,
    sandbox_enabled: bool = False,
    fee_tier: int = 0,
    stop_file: Path | None = None,
    poll_interval_secs: float = DEFAULT_POLL_INTERVAL_SECS,
    max_live_bars: int | None = None,
    warm_ohlcv: pd.DataFrame | None = None,
    poll_fn: Callable[..., pd.DataFrame] | None = None,
    sleep_fn: Callable[[float], Any] | None = None,
    install_signal_handlers: bool = True,
    lookback_days: int | None = None,
    enable_funding_refresh: bool | None = None,
    funding_rate_hourly: float | None = None,
    preferred_fill_model: str = FILL_MODEL_L2_WALK_V1,
    max_book_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS,
    metalabel_enabled: bool = False,
    metalabel_min_p: float = 0.5,
    metalabel_filter: bool = True,
    metalabel_mode: str | None = None,
    execution_mode: str = "shadow",
    now_fn: Callable[[], pd.Timestamp] | None = None,
    enforce_live_boundary: bool | None = None,
    warm_tail_fn: WarmTailFetcher | None = None,
) -> PaperDaemonResult:
    """Start paper daemon: warm history, then process live bars until stop.

    Offline-testable via ``warm_ohlcv``, ``poll_fn``, ``max_live_bars``,
    ``stop_file``, and ``sleep_fn``. Never constructs a live order client.
    The live REST feed refreshes funding (unless disabled) and polls L2 after
    warm-up.

    Default ``execution_mode`` is ``shadow`` (mainnet-honest intents, no submit).
    Offline tests that need paper stamps may pass ``execution_mode="paper"``.

    The injected feed, clock, sleeper and bounded bar count make the
    lifecycle deterministic in tests without changing its no-submit contract.

    Cached warm-up history is topped up from public Hyperliquid candles before
    activation (see :mod:`hypervector.paper.warmup`); a stale cache is never
    spliced in front of fresh bars and a failed refresh aborts start-up.
    """
    mode = str(execution_mode)
    _print_banner(mode)
    sleep = sleep_fn if sleep_fn is not None else time.sleep
    clock = now_fn if now_fn is not None else _utc_now
    export_path = Path(export_dir)
    root = Path(data_root)

    if not export_path.is_dir():
        raise FileNotFoundError(f"export_dir not found: {export_path}")

    loadout = load_strategy_loadout(export_path, strict=True)
    lb = lookback_days
    if lb is None:
        meta_lb = (loadout.meta or {}).get("lookback_days")
        lb = int(meta_lb) if meta_lb is not None else DEFAULT_LOOKBACK
    lb = max(int(lb), FLOOR_LOOKBACK)

    # Live REST path may use L2 book **only after warm-up**. Historical warm-up
    # must never poll live book (wrong prices + REST spam). Offline injected
    # poll_fn keeps book off-network unless the caller sets enable_book_poll later.
    live_rest_feed = poll_fn is None
    if enable_funding_refresh is None:
        enable_funding_refresh = live_rest_feed
    live_book_enabled = live_rest_feed
    enforce_boundary = (
        live_rest_feed if enforce_live_boundary is None else bool(enforce_live_boundary)
    )

    session = PaperSession(
        export_dir=export_path,
        data_root=root,
        conviction=conviction,
        fee_tier=fee_tier,
        sandbox_enabled=sandbox_enabled,
        funding_rate_hourly=funding_rate_hourly,
        enable_funding_refresh=bool(enable_funding_refresh),
        enable_book_poll=False,  # always off for historical warm-up
        preferred_fill_model=str(preferred_fill_model),
        max_book_age_ms=float(max_book_age_ms),
        metalabel_enabled=bool(metalabel_enabled),
        metalabel_min_p=float(metalabel_min_p),
        metalabel_filter=bool(metalabel_filter),
        metalabel_mode=metalabel_mode,
        execution_mode=mode,
        lookback_days=lb,
    )

    # --- warm-up (cache-first history or injected frame) ---
    warmup_provenance: dict[str, Any] = {"mode": "injected"}
    if warm_ohlcv is not None:
        warm_df = warm_ohlcv
    else:
        warm_df, prov = _load_warm_history(
            root,
            symbol=loadout.symbol,
            timeframe=loadout.timeframe,
            lookback_days=lb,
            strict_hl_only=False,
        )
        logger.info(
            "paper warm-up loaded bars=%s provenance=%s",
            len(warm_df),
            prov,
        )
        if warm_df is not None and len(warm_df):
            warm_df, warmup_provenance = refresh_warm_history(
                warm_df,
                symbol=loadout.symbol,
                timeframe=loadout.timeframe,
                now=clock(),
                fetcher=warm_tail_fn,
            )
            logger.info("paper warm-up freshness %s", warmup_provenance)

    if warm_df is None or len(warm_df) == 0:
        raise RuntimeError(
            f"no warm-up bars for {loadout.symbol} {loadout.timeframe} lookback={lb}d"
        )

    activated_at = clock()
    if enforce_boundary:
        loaded_warm_bars = len(warm_df)
        warm_df = completed_bars_at(
            warm_df,
            timeframe=loadout.timeframe,
            observed_at=activated_at,
        )
        logger.info(
            "paper warm-up causal boundary retained=%s excluded=%s",
            len(warm_df),
            loaded_warm_bars - len(warm_df),
        )
        if warm_df.empty:
            raise RuntimeError("warm-up has no causally completed bars at activation")
    session.mark_live(activated_at=activated_at)
    warm_bars = session.warm_up(warm_df)
    session.ensure_session_identity()
    after_ts = session.last_timestamp

    # Live L2 refresh is backend-owned and runs independently of new candle arrival.
    session.enable_book_poll = live_book_enabled
    book_armed_logged = False
    poll_book_in_loop = False
    if live_book_enabled:
        snapshot = session.refresh_book()
        if snapshot is not None:
            logger.info(
                "paper live book armed source=%s bid=%s ask=%s",
                snapshot.source,
                snapshot.best_bid(),
                snapshot.best_ask(),
            )
            book_armed_logged = True

    # --- live feed (REST poll by default; injectable for tests) ---
    # TODO Phase3: prefer HyperliquidDataClient WS when stable
    feed = poll_fn
    if feed is None:
        feed = make_rest_poll_fn(loadout.symbol, loadout.timeframe)

    stop_state = {"reason": None, "stop": False}

    def _request_stop(reason: str) -> None:
        if not stop_state["stop"]:
            stop_state["stop"] = True
            stop_state["reason"] = reason

    prev_handlers: dict[int, Any] = {}
    if install_signal_handlers:

        def _handle_signal(signum: int, _frame: Any) -> None:
            name = (
                signal.Signals(signum).name
                if signum in signal.Signals._value2member_map_
                else str(signum)
            )
            logger.info("paper daemon received %s — stopping", name)
            _request_stop(f"signal_{name}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                prev_handlers[sig] = signal.signal(sig, _handle_signal)
            except (ValueError, OSError):
                # Not in main thread or unsupported — skip
                pass

    live_bars = 0
    empty_polls = 0
    max_empty_when_capped = 3

    try:
        while not stop_state["stop"]:
            if stop_file is not None and Path(stop_file).exists():
                _request_stop("stop_file")
                break

            if max_live_bars is not None and live_bars >= max_live_bars:
                _request_stop("max_live_bars")
                break

            if poll_book_in_loop:
                snapshot = session.refresh_book()
                if snapshot is not None and not book_armed_logged:
                    logger.info(
                        "paper live book armed source=%s bid=%s ask=%s",
                        snapshot.source,
                        snapshot.best_bid(),
                        snapshot.best_ask(),
                    )
                    book_armed_logged = True
            poll_book_in_loop = True

            try:
                new_bars = feed(after_ts=after_ts)
            except Exception as exc:
                logger.warning("paper poll failed: %s", exc)
                new_bars = None

            if (
                new_bars is None
                or not isinstance(new_bars, pd.DataFrame)
                or new_bars.empty
            ):
                empty_polls += 1
                # Offline tests with max_live_bars=0 or exhausted mock: exit soon
                if max_live_bars is not None and max_live_bars == 0:
                    _request_stop("max_live_bars")
                    break
                if max_live_bars is not None and live_bars >= max_live_bars:
                    _request_stop("max_live_bars")
                    break
                if (
                    not live_rest_feed
                    and max_live_bars is not None
                    and empty_polls >= max_empty_when_capped
                    and live_bars > 0
                ):
                    _request_stop("poll_exhausted")
                    break
                if (
                    not live_rest_feed
                    and max_live_bars is not None
                    and empty_polls >= max_empty_when_capped
                    and live_bars == 0
                ):
                    # mock returned nothing; still "ran" live phase
                    _request_stop("poll_exhausted")
                    break
                sleep(float(poll_interval_secs))
                continue

            # Process in timestamp order. Real REST may return a stale cache tail
            # and the still-forming current candle; neither has execution authority.
            frame = new_bars
            if "timestamp" in frame.columns:
                frame = frame.sort_values("timestamp")
            if enforce_boundary:
                catchup, frame = partition_live_bars(
                    frame,
                    timeframe=loadout.timeframe,
                    activated_at=activated_at,
                    observed_at=clock(),
                )
                if not catchup.empty:
                    session.warm_up(catchup)
                    after_ts = pd.Timestamp(catchup["timestamp"].iloc[-1])
                    logger.info("paper catch-up seeded bars=%s", len(catchup))
                if frame.empty:
                    empty_polls += 1
                    sleep(float(poll_interval_secs))
                    continue
            empty_polls = 0
            for _, row in frame.iterrows():
                if max_live_bars is not None and live_bars >= max_live_bars:
                    _request_stop("max_live_bars")
                    break
                if stop_file is not None and Path(stop_file).exists():
                    _request_stop("stop_file")
                    break
                session.on_bar(row)
                live_bars += 1
                ts = row["timestamp"] if "timestamp" in row.index else None
                if ts is not None and not (isinstance(ts, float) and pd.isna(ts)):
                    t = pd.Timestamp(ts)
                    if t.tzinfo is None:
                        t = t.tz_localize("UTC")
                    after_ts = t
                if stop_state["stop"]:
                    break

            if max_live_bars is not None and live_bars >= max_live_bars:
                # Stop at the cap now instead of idling one more poll interval.
                _request_stop("max_live_bars")
            if stop_state["stop"]:
                break
            sleep(float(poll_interval_secs))
    finally:
        for sig, handler in prev_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    if stop_state["reason"] is None:
        stop_state["reason"] = "stop"

    result = PaperDaemonResult(
        run_id=session.run_id,
        decisions_path=session.decisions_path,
        export_dir=session.loadout.export_dir,
        warm_bars=warm_bars,
        live_bars=live_bars,
        bars_processed=session.bars_processed,
        fills_count=session.fills_count,
        stop_reason=str(stop_state["reason"]),
        execution_mode=mode,
        warmup_provenance=warmup_provenance,
    )
    logger.info(
        "paper daemon stopped reason=%s warm=%s live=%s fills=%s",
        result.stop_reason,
        result.warm_bars,
        result.live_bars,
        result.fills_count,
    )
    return result


def _print_banner(execution_mode: str = "shadow") -> None:
    print(banner_for_mode(execution_mode), file=sys.stderr, flush=True)


def _utc_now() -> pd.Timestamp:
    """Return the wall-clock UTC timestamp used for causal feed boundaries."""
    return pd.Timestamp.now(tz="UTC")
