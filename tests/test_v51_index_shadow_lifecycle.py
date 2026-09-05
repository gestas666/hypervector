"""Exact v51 prospective index lifecycle adapter tests."""

from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd

from hypervector.live.hip3_breakout_shadow_specs import SP500_SHADOW_SPEC
from hip3_shadow_lifecycle_fixtures import (
    book,
    candles,
    decision_time,
    decisions,
    funding,
    mark,
)

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json"
)


def test_adapter_uses_exact_v51_entry_and_exit_identity() -> None:
    """Bind v3 SP500 entries to v51 stops, lock, hold, and $5K sizing."""
    module = importlib.import_module("hypervector.research.v51_index_shadow_lifecycle")
    rows = candles(60, None, periods=170)
    entry_time = decision_time(rows, 60) + 1_000
    stop_time = entry_time + 10_000
    entry_ask = 102.01
    stop = entry_ask * (1.0 - 80.0 / 10_000.0)
    report = module.build_v51_index_shadow_lifecycle(
        config_path=_CONFIG,
        stress_path=_STRESS,
        symbol=SP500_SHADOW_SPEC.symbol,
        decision_rows=_sp500_decisions(rows, 60),
        book_rows=(
            _sp500_book(entry_time, 102.0),
            _sp500_book(stop_time, stop - 0.01),
        ),
        candles_15m=rows,
        candles_1m=_pre_entry_bar(entry_time),
        mark_rows=tuple(
            _sp500_mark(mark(ts, stop - 0.01))
            for ts in range(entry_time, stop_time + 1, 1_000)
        ),
        funding_rows=funding(rows),
    )

    assert report["execution_authority"] == "none"
    assert report["runtime_profile_id"].endswith("profit_lock_candidate_v51")
    assert report["replay_contract"]["maximum_stop_bps"] == 120.0
    assert report["replay_contract"]["fixed_stop_bps"] == 80.0
    assert report["replay_contract"]["signal_exit_enabled"] is False
    assert report["replay_contract"]["opposite_entry_exit_enabled"] is True
    assert report["replay_contract"]["notional_usd"] == 5_000.0
    assert report["replay_contract"]["exit_model"] == (
        "fixed_stop_or_opposite_strategy_intent_or_completed_1m_profit_lock_or_24h_"
        "then_next_complete_depth"
    )
    assert report["nominal"]["lifecycles"][0]["exit_reason"] == "stop"


def _sp500_decisions(
    frame: pd.DataFrame, position: int
) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    for row in decisions(frame, eligible_positions={position}):
        copied = {**row, "event_type": "sp500_hip3_breakout_shadow_decision"}
        decision = dict(copied["decision"])
        decision.update(
            symbol=SP500_SHADOW_SPEC.symbol,
            provider_id=SP500_SHADOW_SPEC.provider_id,
            profile_id=SP500_SHADOW_SPEC.profile_id,
        )
        copied["decision"] = decision
        output.append(copied)
    return tuple(output)


def _sp500_book(timestamp_ms: int, midpoint: float) -> dict[str, object]:
    row = book(timestamp_ms, midpoint)
    row["profile_id"] = SP500_SHADOW_SPEC.ledger_profile_id
    payload = dict(row["payload"])
    payload["symbol"] = SP500_SHADOW_SPEC.symbol
    row["payload"] = payload
    return row


def _sp500_mark(row: dict[str, object]) -> dict[str, object]:
    return {**row, "symbol": SP500_SHADOW_SPEC.symbol}


def _pre_entry_bar(entry_ms: int) -> pd.DataFrame:
    timestamp = entry_ms // 60_000 * 60_000 - 60_000
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([timestamp], unit="ms", utc=True),
            "open": [102.0],
            "high": [102.1],
            "low": [101.9],
            "close": [102.0],
            "source": ["hl"],
        }
    )
