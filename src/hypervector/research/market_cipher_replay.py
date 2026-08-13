"""Causal multi-asset shared-capital replay for Market Cipher candidates."""

from __future__ import annotations

import pandas as pd

from hypervector.research.market_cipher_replay_inputs import (
    prepare_replay_candidates,
    replay_bars_at_time,
    replay_event_times,
    validate_replay_bars,
)
from hypervector.research.market_cipher_replay_lifecycle import (
    advance_open_positions,
    force_end_closes,
    update_marked_drawdown,
)
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    MarketCipherReplayReport,
)
from hypervector.research.market_cipher_replay_orders import (
    execute_pending_exits,
    fill_replay_candidates,
)
from hypervector.research.market_cipher_replay_reporting import (
    build_market_cipher_replay_report,
)
from hypervector.research.market_cipher_replay_state import ReplayState


def evaluate_market_cipher_replay(
    bars_by_symbol: dict[str, pd.DataFrame],
    signals: pd.DataFrame,
    config: MarketCipherReplayConfig | None = None,
) -> MarketCipherReplayReport:
    """Replay close-known signals through one chronological funded portfolio."""
    cfg = config or MarketCipherReplayConfig()
    validate_replay_bars(bars_by_symbol)
    for symbol in bars_by_symbol:
        cfg.venue_max_leverage_for(symbol)
    scheduled, initial_rejections = prepare_replay_candidates(
        bars_by_symbol, signals, cfg
    )
    state = ReplayState(cfg.initial_equity, cfg.initial_equity)
    state.rejections.extend(initial_rejections)
    for timestamp in replay_event_times(bars_by_symbol):
        available = replay_bars_at_time(bars_by_symbol, timestamp)
        execute_pending_exits(state, available, timestamp, cfg)
        fill_replay_candidates(state, scheduled.get(timestamp, []), cfg)
        advance_open_positions(state, available, timestamp, cfg)
        update_marked_drawdown(state, available)
    force_end_closes(state, bars_by_symbol, cfg)
    return build_market_cipher_replay_report(
        initial_equity=cfg.initial_equity,
        final_equity=state.equity,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        maximum_concurrent_positions=state.maximum_concurrent_positions,
        trades=state.trades,
        rejections=state.rejections,
    )
