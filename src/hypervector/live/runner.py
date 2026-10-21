"""Live daemon lifecycle: policy gates → warm-up (no place) → live place phase.

Reuses paper daemon shell patterns (warm + poll loop). Never used by paper path.

Execution authority is causal: warm-up history only seeds indicators, bars
that closed before activation (or that are older than the latest closed bar)
are recorded without evaluation, the still-forming candle is never processed,
and the armed phase starts flat against a venue position read.
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
from hypervector.live.engine import LiveReconciliationError
from hypervector.live.exec_client import (
    HyperliquidLiveExecClient,
    PlaceTransport,
    create_live_exec_client,
)
from hypervector.live.policy import LivePolicy
from hypervector.live.session import LiveIntentError, LiveSession
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.live_node import (
    DEFAULT_POLL_INTERVAL_SECS,
    completed_bars_at,
    filter_bars_after,
    make_rest_poll_fn,
    partition_live_bars,
    timeframe_delta,
)
from hypervector.runtime_lock import canonical_live_root, generic_live_runtime_lock

logger = logging.getLogger(__name__)

LIVE_BANNER = "LIVE MODE — mainnet venue orders when armed (fail-closed gates)"

# REST poll window; warm-up history must end inside it so the feed can bridge.
LIVE_POLL_LOOKBACK_DAYS = 1


@dataclass(frozen=True)
class LiveDaemonResult:
    run_id: str
    decisions_path: Path
    export_dir: Path
    warm_bars: int
    live_bars: int
    bars_processed: int
    fills_count: int
    places_count: int
    stop_reason: str
    execution_mode: str = "live"
    cancel_attempted: bool = False
    cancel_ok: bool | None = None
    cancel_error: str | None = None
    # Live-phase bars recorded without execution authority (catch-up / stale).
    catchup_bars: int = 0
    # Engine position at stop (venue-reconciled after every live order). The
    # daemon never flattens on stop, so a non-zero value is open exposure.
    position_qty: float = 0.0


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def start_live_daemon(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    policy: LivePolicy,
    wallet_address: str | None = None,
    private_key: str | None = None,
    transport: PlaceTransport | None = None,
    conviction: float = 0.5,
    fee_tier: int = 0,
    stop_file: Path | None = None,
    poll_interval_secs: float = DEFAULT_POLL_INTERVAL_SECS,
    max_live_bars: int | None = None,
    warm_ohlcv: pd.DataFrame | None = None,
    poll_fn: Callable[..., pd.DataFrame] | None = None,
    sleep_fn: Callable[[float], Any] | None = None,
    install_signal_handlers: bool = True,
    lookback_days: int | None = None,
    funding_rate_hourly: float | None = None,
    now_fn: Callable[[], pd.Timestamp] | None = None,
    enforce_live_boundary: bool | None = None,
    account_lock_root: Path | str | None = None,
) -> LiveDaemonResult:
    """Start live daemon after policy.require_start(); place only in live phase.

    Only the latest closed bar of each poll can trade, and only after warm-up.
    With the default REST feed (``poll_fn`` omitted) the wall-clock boundary is
    always enforced: warm-up keeps only candles complete at activation, bars that
    closed by activation are catch-up, and a bar older than the most recently
    closed candle is stale; neither catch-up nor stale bars nor the forming
    candle have execution authority. ``now_fn`` and ``enforce_live_boundary``
    let offline tests drive that boundary with a deterministic clock.

    The daemon owns the shared live account for its whole run, from before the
    exec client exists through the stop cancel: it takes
    :func:`generic_live_runtime_lock` on ``account_lock_root`` (default: the
    cohort's canonical ``data/live``, never ``data_root``) and raises
    ``RuntimeLockError`` before any venue call while the cohort or another live
    backend owns the account.

    Offline-testable via warm_ohlcv, poll_fn, transport, max_live_bars, sleep_fn.
    Raises on technical failure (unreadable or non-flat venue position before
    arming, venue/engine position drift after an order, an armed-phase strategy
    failure, warm-up gaps the feed cannot bridge).
    """
    # Fail closed before any client construction or IO side effects beyond layout.
    policy.require_start()

    if wallet_address is None or private_key is None:
        raise ValueError("wallet_address and private_key required for live daemon")

    export_path = Path(export_dir)
    if not export_path.is_dir():
        raise FileNotFoundError(f"export_dir not found: {export_path}")
    loadout = load_strategy_loadout(export_path, strict=True)
    timeframe = loadout.timeframe
    bar_interval = timeframe_delta(timeframe)  # unsupported timeframe: refuse now
    clock = now_fn if now_fn is not None else _utc_now
    injected_feed = poll_fn is not None
    enforce = (
        not injected_feed
        if enforce_live_boundary is None
        else bool(enforce_live_boundary)
    )

    lock_root = (
        Path(account_lock_root)
        if account_lock_root is not None
        else canonical_live_root()
    )
    with generic_live_runtime_lock(lock_root):
        client = create_live_exec_client(
            policy,
            wallet_address=wallet_address,
            private_key=private_key,
            transport=transport,
        )

        print(LIVE_BANNER, file=sys.stderr, flush=True)
        sleep = sleep_fn if sleep_fn is not None else time.sleep
        root = Path(data_root)
        lb = lookback_days
        if lb is None:
            meta_lb = (loadout.meta or {}).get("lookback_days")
            lb = int(meta_lb) if meta_lb is not None else DEFAULT_LOOKBACK
        lb = max(int(lb), FLOOR_LOOKBACK)

        session = LiveSession(
            export_dir=export_path,
            data_root=root,
            client=client,
            max_notional_usd=policy.max_notional_usd,
            conviction=conviction,
            fee_tier=fee_tier,
            funding_rate_hourly=funding_rate_hourly,
            place_enabled=False,  # warm-up never places
        )

        # Activation is stamped before the warm-up fetch: a candle still forming
        # when the history snapshot was taken must not be seeded as complete just
        # because it closed while the (multi-venue) load was still running.
        activated_at = _utc(clock())
        if warm_ohlcv is not None:
            warm_df = warm_ohlcv
        else:
            # Never decide on a stale cache: refresh history at every live start.
            warm_df, prov = load_research_history(
                root,
                symbol=loadout.symbol,
                timeframe=timeframe,
                lookback_days=lb,
                force_refresh=True,
            )
            logger.info("live warm-up loaded bars=%s provenance=%s", len(warm_df), prov)

        if warm_df is None or len(warm_df) == 0:
            raise RuntimeError(
                f"no warm-up bars for {loadout.symbol} {timeframe} lookback={lb}d"
            )

        if enforce:
            warm_df = _causal_warmup(
                warm_df,
                timeframe=timeframe,
                bar_interval=bar_interval,
                activated_at=activated_at,
            )

        warm_bars = session.seed_history(warm_df)
        session.ensure_session_identity()
        after_ts = session.last_timestamp

        # Live phase: the venue must be flat for this coin, then arm venue place.
        _require_flat_venue(client, loadout.symbol)
        session.enable_live_place()

        feed = poll_fn
        if feed is None:
            feed = make_rest_poll_fn(
                loadout.symbol, timeframe, lookback_days=LIVE_POLL_LOOKBACK_DAYS
            )

        stop_state: dict[str, Any] = {"reason": None, "stop": False}

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
                logger.info("live daemon received %s — stopping", name)
                _request_stop(f"signal_{name}")

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    prev_handlers[sig] = signal.signal(sig, _handle_signal)
                except (ValueError, OSError):
                    pass

        live_bars = 0
        catchup_bars = 0
        empty_polls = 0
        max_empty_when_capped = 3
        failure: LiveReconciliationError | LiveIntentError | None = None

        try:
            while not stop_state["stop"]:
                if stop_file is not None and Path(stop_file).exists():
                    _request_stop("stop_file")
                    break
                if max_live_bars is not None and live_bars >= max_live_bars:
                    _request_stop("max_live_bars")
                    break

                # Stamp the observation before the request: the snapshot is taken
                # somewhere inside the round trip, so only candles closed by the
                # time the request left are guaranteed final in it.
                observed_at = _utc(clock()) if enforce else None
                try:
                    new_bars = feed(after_ts=after_ts)
                except Exception as exc:
                    logger.warning("live poll failed: %s", exc)
                    new_bars = None

                frame = _unseen_bars(new_bars, after_ts=after_ts)
                observe = frame.iloc[0:0]
                actionable: pd.Series | None = None
                if not frame.empty:
                    observe, actionable = _split_authority(
                        frame,
                        timeframe=timeframe,
                        bar_interval=bar_interval,
                        activated_at=activated_at,
                        observed_at=observed_at,
                    )

                if observe.empty and actionable is None:
                    # Nothing new, or only the still-forming candle.
                    empty_polls += 1
                    if (
                        injected_feed
                        and max_live_bars is not None
                        and empty_polls >= max_empty_when_capped
                    ):
                        _request_stop("poll_exhausted")
                        break
                    sleep(float(poll_interval_secs))
                    continue

                empty_polls = 0
                if not observe.empty:
                    for _, row in observe.iterrows():
                        session.observe_bar(row)
                        catchup_bars += 1
                    after_ts = _utc(observe["timestamp"].iloc[-1])
                    logger.info(
                        "live recorded %s bars without order authority "
                        "(catch-up/stale) %s..%s",
                        len(observe),
                        observe["timestamp"].iloc[0],
                        observe["timestamp"].iloc[-1],
                    )

                if actionable is not None:
                    if max_live_bars is not None and live_bars >= max_live_bars:
                        _request_stop("max_live_bars")
                        break
                    if stop_file is not None and Path(stop_file).exists():
                        _request_stop("stop_file")
                        break
                    try:
                        session.on_bar(actionable)
                    except LiveReconciliationError as exc:
                        failure = exc
                        _request_stop("venue_position_mismatch")
                    except LiveIntentError as exc:
                        failure = exc
                        _request_stop("intent_error")
                    live_bars += 1
                    after_ts = _utc(actionable["timestamp"])

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

        # F4 kill: cancel resting orders this daemon placed after live phase armed.
        cancel_attempted = False
        cancel_ok: bool | None = None
        cancel_error: str | None = None
        if session.engine.place_enabled:
            cancel_attempted = True
            try:
                cancel_result = client.cancel_all(symbol=loadout.symbol)
                cancel_ok = bool(cancel_result.submitted)
                cancel_error = cancel_result.error
                if cancel_ok:
                    logger.info(
                        "live kill cancel_all ok: %s",
                        cancel_result.detail or cancel_result.venue_order_id,
                    )
                else:
                    logger.warning("live kill cancel_all failed: %s", cancel_error)
            except Exception as exc:  # noqa: BLE001 — never block stop summary
                cancel_ok = False
                cancel_error = str(exc)
                logger.warning("live kill cancel_all exception: %s", exc)

        result = LiveDaemonResult(
            run_id=session.run_id,
            decisions_path=session.decisions_path,
            export_dir=session.loadout.export_dir,
            warm_bars=warm_bars,
            live_bars=live_bars,
            bars_processed=session.bars_processed,
            fills_count=session.fills_count,
            places_count=session.places_count,
            stop_reason=str(stop_state["reason"]),
            execution_mode="live",
            cancel_attempted=cancel_attempted,
            cancel_ok=cancel_ok,
            cancel_error=cancel_error,
            catchup_bars=catchup_bars,
            position_qty=float(session.engine.position.qty),
        )
        logger.info(
            "live daemon stopped reason=%s warm=%s catchup=%s live=%s fills=%s "
            "places=%s cancel=%s",
            result.stop_reason,
            result.warm_bars,
            result.catchup_bars,
            result.live_bars,
            result.fills_count,
            result.places_count,
            result.cancel_attempted,
        )
        if failure is not None:
            # Technical failure: the open exposure is no longer under engine
            # control (drift) or its exits can no longer be evaluated (intent).
            raise failure
        return result


def _causal_warmup(
    warm_df: pd.DataFrame,
    *,
    timeframe: str,
    bar_interval: pd.Timedelta,
    activated_at: pd.Timestamp,
) -> pd.DataFrame:
    """Keep candles complete at activation; refuse a gap the feed cannot bridge."""
    loaded = len(warm_df)
    completed = completed_bars_at(
        warm_df, timeframe=timeframe, observed_at=activated_at
    )
    logger.info(
        "live warm-up causal boundary retained=%s excluded=%s",
        len(completed),
        loaded - len(completed),
    )
    if completed.empty:
        raise RuntimeError("warm-up has no causally completed bars at activation")
    last_close = _utc(completed["timestamp"].max()) + bar_interval
    horizon = activated_at - pd.Timedelta(days=LIVE_POLL_LOOKBACK_DAYS)
    if last_close < horizon:
        raise RuntimeError(
            f"warm-up history ends at {last_close.isoformat()}, more than the "
            f"{LIVE_POLL_LOOKBACK_DAYS}-day live poll window before activation "
            f"{activated_at.isoformat()}; the feed cannot bridge that gap"
        )
    return completed


def _require_flat_venue(client: HyperliquidLiveExecClient, symbol: str) -> None:
    """Arm only when the venue holds no position in the coin this daemon trades."""
    try:
        venue_qty = client.venue_position(symbol)
    except Exception as exc:  # noqa: BLE001 — unreadable venue state is technical
        raise RuntimeError(
            f"cannot read the venue position for {symbol} before arming: {exc}"
        ) from exc
    if venue_qty != 0.0:
        raise RuntimeError(
            f"venue already holds {venue_qty!r} {symbol}; the generic live daemon "
            "starts flat and will not adopt, add to or close a position it did not "
            "open — flatten it first or run it under 'cohort live'"
        )


def _unseen_bars(new_bars: Any, *, after_ts: pd.Timestamp | None) -> pd.DataFrame:
    """Normalize one poll to unique, time-ordered bars strictly after ``after_ts``."""
    if new_bars is None or not isinstance(new_bars, pd.DataFrame) or new_bars.empty:
        return pd.DataFrame()
    frame = filter_bars_after(new_bars, after_ts=after_ts)
    if frame.empty or "timestamp" not in frame.columns:
        return pd.DataFrame()
    frame = frame.sort_values("timestamp", kind="mergesort")
    frame = frame.drop_duplicates(subset="timestamp", keep="last")
    return frame.reset_index(drop=True)


def _split_authority(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    bar_interval: pd.Timedelta,
    activated_at: pd.Timestamp,
    observed_at: pd.Timestamp | None,
) -> tuple[pd.DataFrame, pd.Series | None]:
    """Return ``(bars to record without authority, the one bar that may trade)``.

    With an observation time, only causally complete candles are kept, those
    closing by activation are catch-up, and the newest complete candle trades
    only if it is the most recently closed one. Without one (an injected test
    feed), the newest bar of the poll is the only candidate.
    """
    if observed_at is not None:
        catchup, live = partition_live_bars(
            frame,
            timeframe=timeframe,
            activated_at=activated_at,
            observed_at=observed_at,
        )
    else:
        catchup, live = frame.iloc[0:0], frame
    if live.empty:
        return catchup, None
    latest = live.iloc[-1]
    if observed_at is not None:
        latest_close = _utc(latest["timestamp"]) + bar_interval
        if latest_close <= observed_at - bar_interval:
            return _stack(catchup, live), None
    return _stack(catchup, live.iloc[:-1]), latest


def _stack(first: pd.DataFrame, second: pd.DataFrame) -> pd.DataFrame:
    if first.empty:
        return second.reset_index(drop=True)
    if second.empty:
        return first.reset_index(drop=True)
    return pd.concat([first, second], ignore_index=True)
