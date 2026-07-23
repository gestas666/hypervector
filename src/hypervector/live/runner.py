"""Live daemon lifecycle: policy gates → warm-up (no place) → live place phase.

Reuses paper daemon shell patterns (warm + poll loop). Never used by paper path.
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
from hypervector.live.exec_client import (
    PlaceTransport,
    create_live_exec_client,
)
from hypervector.live.policy import LivePolicy
from hypervector.live.session import LiveSession
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.live_node import DEFAULT_POLL_INTERVAL_SECS, make_rest_poll_fn

logger = logging.getLogger(__name__)

LIVE_BANNER = "LIVE MODE — mainnet venue orders when armed (fail-closed gates)"


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
) -> LiveDaemonResult:
    """Start live daemon after policy.require_start(); place only in live phase.

    Offline-testable via warm_ohlcv, poll_fn, transport, max_live_bars, sleep_fn.
    """
    # Fail closed before any client construction or IO side effects beyond layout.
    policy.require_start()

    if wallet_address is None or private_key is None:
        raise ValueError("wallet_address and private_key required for live daemon")

    client = create_live_exec_client(
        policy,
        wallet_address=wallet_address,
        private_key=private_key,
        transport=transport,
    )

    print(LIVE_BANNER, file=sys.stderr, flush=True)
    sleep = sleep_fn if sleep_fn is not None else time.sleep
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

    if warm_ohlcv is not None:
        warm_df = warm_ohlcv
    else:
        warm_df, prov = load_research_history(
            root,
            symbol=loadout.symbol,
            timeframe=loadout.timeframe,
            lookback_days=lb,
            force_refresh=False,
        )
        logger.info("live warm-up loaded bars=%s provenance=%s", len(warm_df), prov)

    if warm_df is None or len(warm_df) == 0:
        raise RuntimeError(
            f"no warm-up bars for {loadout.symbol} {loadout.timeframe} lookback={lb}d"
        )

    warm_bars = session.process_frame(warm_df)
    session.ensure_session_identity()
    after_ts = session.last_timestamp

    # Live phase: arm venue place.
    session.enable_live_place()

    feed = poll_fn
    if feed is None:
        feed = make_rest_poll_fn(loadout.symbol, loadout.timeframe)

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

            try:
                new_bars = feed(after_ts=after_ts)
            except Exception as exc:
                logger.warning("live poll failed: %s", exc)
                new_bars = None

            if new_bars is None or not isinstance(new_bars, pd.DataFrame) or new_bars.empty:
                empty_polls += 1
                if max_live_bars is not None and max_live_bars == 0:
                    _request_stop("max_live_bars")
                    break
                if max_live_bars is not None and empty_polls >= max_empty_when_capped:
                    _request_stop("poll_exhausted")
                    break
                sleep(float(poll_interval_secs))
                continue

            empty_polls = 0
            frame = new_bars
            if "timestamp" in frame.columns:
                frame = frame.sort_values("timestamp")
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
    )
    logger.info(
        "live daemon stopped reason=%s warm=%s live=%s fills=%s places=%s",
        result.stop_reason,
        result.warm_bars,
        result.live_bars,
        result.fills_count,
        result.places_count,
    )
    return result
