"""Exact SNDK correction reuses durable prospective pressure-state semantics."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_breakout_shadow_specs import Hip3BreakoutShadowSpec
from hypervector.live.mu_hip3_breakout_shadow import (
    MuHip3BreakoutShadowCollector,
    MuHip3BreakoutShadowCursor,
)
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    _append_decision_once,
    _load_cursor,
    _write_cursor,
)
from hypervector.live.hip3_fresh15_journal_provider import Hip3Fresh15JournalCollector
from hypervector.live.mu_hip3_preclose_pressure import MuPreclosePressureEvidence
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

_SPEC = Hip3BreakoutShadowSpec(
    "xyz:SNDK",
    "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v4",
    "sndk_fresh15_pressure_shadow_research_v4",
    "sndk_fresh15_shadow_xyz:sndk",
    Hip3BreakoutPressureConfig(32, 21, 55, 0.35, 120.0),
)
_BAR_MS = 900_000
_AGE_MS = 1000
_PERIODS = 101
_BASE_PRICE = 1000


def _bars() -> pd.DataFrame:
    times = pd.date_range("2026-05-18T00:00:00Z", periods=_PERIODS, freq="15min")
    close = pd.Series([_BASE_PRICE - position for position in range(_PERIODS)])
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 10.0,
        }
    )


def _evidence(boundary: int, *, fresh: bool = True) -> MuPreclosePressureEvidence:
    return MuPreclosePressureEvidence(
        _SPEC.symbol,
        boundary - _BAR_MS,
        boundary,
        boundary + _AGE_MS,
        "hyperliquid_mainnet_l2_rest",
        boundary - _AGE_MS,
        boundary - _AGE_MS,
        2 if fresh else 1,
        _AGE_MS,
        -0.6,
        fresh,
        True,
        "fresh" if fresh else "insufficient_snapshots",
    )


class _Source:
    def __init__(self, *, fresh: bool = True) -> None:
        self.fresh = fresh

    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        assert symbol == _SPEC.symbol
        return replace(
            _evidence(bar_close_ms, fresh=self.fresh), observed_at_ms=observed_at_ms
        )


def _cursor(*, prior_short: bool | None = True) -> MuHip3BreakoutShadowCursor:
    boundary = int(_bars().timestamp.iloc[-1].timestamp() * 1000)
    pressure = (
        None
        if prior_short is None
        else replace(_evidence(boundary), imbalance_10=-0.6 if prior_short else 0.0)
    )
    return MuHip3BreakoutShadowCursor(
        _SPEC.provider_id,
        _SPEC.profile_id,
        _SPEC.symbol,
        boundary,
        boundary - _BAR_MS,
        boundary + _AGE_MS,
        False if prior_short is not None else None,
        prior_short,
        pressure,
    )


def _observed() -> pd.Timestamp:
    return _bars().timestamp.iloc[-1] + pd.Timedelta(milliseconds=_BAR_MS + _AGE_MS)


@pytest.mark.parametrize("restart", [False, True])
def test_continuing_sndk_breakout_does_not_refire(
    tmp_path: Path, restart: bool
) -> None:
    """A known continuous short state survives both memory and disk restart."""
    cursor = _cursor()
    if restart:
        path = tmp_path / "cursor.json"
        _write_cursor(path, cursor)
        cursor = _load_cursor(path)
    collector = MuHip3BreakoutShadowCollector(pressure_source=_Source(), spec=_SPEC)
    batch = collector(
        _bars(), symbol=_SPEC.symbol, observed_at=_observed(), cursor=cursor
    )
    assert batch.decisions[0].eligible is False
    assert batch.decisions[0].pressure_state_history_complete is True
    assert batch.next_cursor.short_raw is True
    assert batch.intents == ()


def test_genuine_new_short_state_remains_eligible() -> None:
    """Correcting repeated onset does not suppress a known false-to-true state."""
    collector = MuHip3BreakoutShadowCollector(pressure_source=_Source(), spec=_SPEC)
    batch = collector(
        _bars(),
        symbol=_SPEC.symbol,
        observed_at=_observed(),
        cursor=_cursor(prior_short=False),
    )
    assert batch.decisions[0].eligible is True
    assert batch.decisions[0].side == "short"
    assert batch.next_cursor.short_raw is True
    assert batch.execution_authority == "none"


@pytest.mark.parametrize("prior_short,fresh", [(None, True), (False, False)])
def test_unknown_history_and_insufficient_pressure_are_explicit(
    prior_short: bool | None,
    fresh: bool,
) -> None:
    """Absent causal evidence cannot be silently reconstructed as a new onset."""
    collector = MuHip3BreakoutShadowCollector(
        pressure_source=_Source(fresh=fresh), spec=_SPEC
    )
    batch = collector(
        _bars(),
        symbol=_SPEC.symbol,
        observed_at=_observed(),
        cursor=_cursor(prior_short=prior_short),
    )
    assert batch.decisions[0].eligible is False
    assert (
        not batch.decisions[0].pressure_state_history_complete
        or not batch.decisions[0].pressure_fresh
    )


def test_delayed_observation_cannot_retroactively_fire() -> None:
    """A decision beyond the frozen 15-second observation limit is censored."""
    collector = MuHip3BreakoutShadowCollector(pressure_source=_Source(), spec=_SPEC)
    batch = collector(
        _bars(),
        symbol=_SPEC.symbol,
        observed_at=_observed() + pd.Timedelta(seconds=15),
        cursor=_cursor(prior_short=False),
    )
    assert batch.decisions == ()
    assert batch.retroactive_decisions_censored == 1


@pytest.mark.parametrize("prior_short,entries", [(True, 0), (False, 1), (None, 0)])
def test_durable_sndk_journal_preserves_corrected_entry_authority(
    tmp_path: Path,
    prior_short: bool | None,
    entries: int,
) -> None:
    """The adapter consumes actual corrected writer output with exact v4 identity."""
    collector = MuHip3BreakoutShadowCollector(pressure_source=_Source(), spec=_SPEC)
    batch = collector(
        _bars(),
        symbol=_SPEC.symbol,
        observed_at=_observed(),
        cursor=_cursor(prior_short=prior_short),
    )
    path = tmp_path / "decisions.jsonl"
    _append_decision_once(path, batch.decisions[0])
    adapter = Hip3Fresh15JournalCollector(journals={_SPEC.symbol: path})
    result = adapter(
        _bars(),
        symbol=_SPEC.symbol,
        observed_at=_observed(),
        after_decision_time_ms=_cursor().decision_time_ms,
    )
    assert len(result.intents) == entries
    assert result.evaluations[0].strategy_id == _SPEC.provider_id
