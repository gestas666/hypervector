"""Report-only MU breakout shadow collector contracts."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_STRATEGY,
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
    HIP3_BREAKOUT_INDEX_STRATEGY,
    HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
    HIP3_STRATEGIES,
    HIP3_SWING_COMMODITY_STRATEGY,
    HIP3_SWING_INDEX_STRATEGY,
)
from hypervector.live.mu_hip3_breakout_shadow import (
    MU_SHADOW_PROFILE_ID,
    MU_SHADOW_PROVIDER_ID,
    MuHip3BreakoutShadowCollector,
    MuHip3BreakoutShadowCursor,
)
from hypervector.live.mu_hip3_preclose_pressure import (
    MuAssetLedgerBinding,
    MuHip3LedgerPreclosePressureSource,
    MuPreclosePressureEvidence,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-09T12:00:00Z", periods=40, freq="15min")
    closes = [100.0] * 39 + [102.0]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": 10.0,
        }
    )


class _Source:
    def __init__(self, evidence: MuPreclosePressureEvidence) -> None:
        self.evidence = evidence
        self.calls: list[tuple[int, int, int]] = []

    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        self.calls.append((bar_open_ms, bar_close_ms, observed_at_ms))
        return replace(
            self.evidence,
            symbol=symbol,
            bar_open_ms=bar_open_ms,
            bar_close_ms=bar_close_ms,
            observed_at_ms=observed_at_ms,
            last_exchange_ts_ms=bar_close_ms - 1_000,
            last_recv_ts_ms=min(observed_at_ms, bar_close_ms),
            end_boundary_age_ms=1_000,
        )


class _CurrentOnlySource(_Source):
    def __init__(
        self,
        evidence: MuPreclosePressureEvidence,
        current_close_ms: int,
    ) -> None:
        super().__init__(evidence)
        self._current_close_ms = current_close_ms

    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        value = super().completed_bar(
            symbol,
            bar_open_ms=bar_open_ms,
            bar_close_ms=bar_close_ms,
            observed_at_ms=observed_at_ms,
        )
        if bar_close_ms == self._current_close_ms:
            return value
        return replace(value, fresh=False, scan_complete=False, status="truncated")


def _evidence(*, fresh: bool = True) -> MuPreclosePressureEvidence:
    return MuPreclosePressureEvidence(
        symbol="xyz:MU",
        bar_open_ms=0,
        bar_close_ms=1,
        observed_at_ms=1,
        source="hyperliquid_mainnet_l2_rest",
        last_exchange_ts_ms=0,
        last_recv_ts_ms=1,
        snapshot_count=2,
        end_boundary_age_ms=1,
        imbalance_10=0.6,
        fresh=fresh,
        scan_complete=True,
        status="fresh" if fresh else "stale",
    )


def _cursor(
    boundary: pd.Timestamp = pd.Timestamp("2026-08-09T21:45:00Z"),
    *,
    long_raw: bool | None = False,
    short_raw: bool | None = False,
    pressure_fresh: bool = True,
) -> MuHip3BreakoutShadowCursor:
    boundary_ms = int(boundary.timestamp() * 1_000)
    evidence = None
    if long_raw is not None and short_raw is not None:
        evidence = replace(
            _evidence(fresh=pressure_fresh),
            bar_open_ms=boundary_ms - 900_000,
            bar_close_ms=boundary_ms,
            observed_at_ms=boundary_ms + 1_000,
            last_exchange_ts_ms=boundary_ms - 1_000,
            last_recv_ts_ms=boundary_ms,
            end_boundary_age_ms=1_000,
        )
    return MuHip3BreakoutShadowCursor(
        MU_SHADOW_PROVIDER_ID,
        MU_SHADOW_PROFILE_ID,
        "xyz:MU",
        boundary_ms,
        boundary_ms - 900_000,
        boundary_ms + 1_000,
        long_raw,
        short_raw,
        evidence,
    )


def test_shadow_uses_frozen_identity_and_emits_pressure_provenance() -> None:
    observed = pd.Timestamp("2026-08-09T22:00:01Z")
    source = _Source(_evidence())
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)
    cursor = _cursor()

    batch = collector(
        _bars(),
        symbol="xyz:MU",
        observed_at=observed,
        cursor=cursor,
    )

    assert collector.config == Hip3BreakoutPressureConfig(32, 9, 21, 0.1, 80.0)
    assert batch.execution_authority == "none"
    assert batch.intents == ()
    assert len(batch.decisions) == 1
    decision = batch.decisions[0]
    assert decision.provider_id == MU_SHADOW_PROVIDER_ID
    assert decision.profile_id == MU_SHADOW_PROFILE_ID
    assert decision.pressure_fresh is True
    assert decision.pressure_source == "hyperliquid_mainnet_l2_rest"
    assert decision.pressure_scan_complete is True
    assert decision.pressure_snapshot_count == 2
    assert decision.pressure_end_boundary_age_ms == 1_000
    assert decision.pressure_exchange_ts_ms == decision.decision_time_ms - 1_000
    assert decision.pressure_recv_ts_ms <= int(observed.timestamp() * 1_000)
    assert decision.observed_at_ms == int(observed.timestamp() * 1_000)
    assert decision.decision_delay_ms == 1_000
    assert decision.prior_decision_boundary_ms == cursor.decision_time_ms
    assert decision.prospective is True
    assert decision.pressure_state_history_complete is True
    assert decision.eligible is True
    assert batch.next_cursor.decision_time_ms == decision.decision_time_ms


def test_stale_pressure_is_zeroed_and_cannot_fire() -> None:
    observed = pd.Timestamp("2026-08-09T22:00:01Z")
    source = _Source(_evidence(fresh=False))
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)

    batch = collector(
        _bars(),
        symbol="xyz:MU",
        observed_at=observed,
        cursor=_cursor(),
    )

    assert len(batch.decisions) == 1
    assert batch.decisions[0].eligible is False
    assert batch.decisions[0].decision_imbalance_10 == 0.0


def test_restart_boundary_prevents_old_retro_entry_and_pressure_scan() -> None:
    observed = pd.Timestamp("2026-08-09T22:00:01Z")
    source = _Source(_evidence())
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)
    current_cursor = _cursor(pd.Timestamp("2026-08-09T22:00:00Z"))

    batch = collector(
        _bars(),
        symbol="xyz:MU",
        observed_at=observed,
        cursor=current_cursor,
    )

    assert batch.decisions == ()
    assert batch.latest_decision_time_ms == current_cursor.decision_time_ms
    assert batch.next_cursor == current_cursor
    assert source.calls == []


def test_missing_restart_cursor_fails_before_pressure_scan() -> None:
    source = _Source(_evidence())
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)

    with pytest.raises(ValueError, match="restart cursor"):
        collector(
            _bars(),
            symbol="xyz:MU",
            observed_at=pd.Timestamp("2026-08-09T22:00:01Z"),
            cursor=None,
        )

    assert source.calls == []


def test_late_unseen_decision_is_censored_as_retroactive() -> None:
    source = _Source(_evidence())
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)

    batch = collector(
        _bars(),
        symbol="xyz:MU",
        observed_at=pd.Timestamp("2026-08-10T00:00:00Z"),
        cursor=_cursor(),
    )

    assert batch.decisions == ()
    assert batch.retroactive_decisions_censored == 1
    assert source.calls == []
    assert batch.next_cursor.decision_time_ms == int(
        pd.Timestamp("2026-08-09T22:00:00Z").timestamp() * 1_000
    )
    assert batch.next_cursor.long_raw is None


def test_unresolved_prior_pressure_state_cannot_create_spurious_onset() -> None:
    bars = _bars()
    bars["open"] = [100.0 + position for position in range(len(bars))]
    bars["close"] = bars["open"]
    bars["high"] = bars["open"] + 0.1
    bars["low"] = bars["open"] - 0.1
    observed = pd.Timestamp("2026-08-09T22:00:01Z")
    current_close = int(pd.Timestamp("2026-08-09T22:00:00Z").timestamp() * 1_000)
    complete = MuHip3BreakoutShadowCollector(pressure_source=_Source(_evidence()))(
        bars,
        symbol="xyz:MU",
        observed_at=observed,
        cursor=_cursor(long_raw=True, short_raw=False),
    )
    truncated = MuHip3BreakoutShadowCollector(
        pressure_source=_CurrentOnlySource(_evidence(), current_close)
    )(
        bars,
        symbol="xyz:MU",
        observed_at=observed,
        cursor=_cursor(long_raw=None, short_raw=None),
    )

    assert complete.decisions[0].side is None
    assert truncated.decisions[0].side == "long"
    assert truncated.decisions[0].pressure_state_history_complete is False
    assert truncated.decisions[0].eligible is False


class _DelayedPriorReceiptSource(_Source):
    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        if bar_close_ms < int(pd.Timestamp("2026-08-09T22:00:00Z").timestamp() * 1_000):
            raise AssertionError("frozen prior pressure must not be reconstructed")
        return super().completed_bar(
            symbol,
            bar_open_ms=bar_open_ms,
            bar_close_ms=bar_close_ms,
            observed_at_ms=observed_at_ms,
        )


def test_delayed_prior_receipt_cannot_rewrite_frozen_onset_state() -> None:
    bars = _bars()
    bars["open"] = [100.0 + position for position in range(len(bars))]
    bars["close"] = bars["open"]
    bars["high"] = bars["open"] + 0.1
    bars["low"] = bars["open"] - 0.1
    source = _DelayedPriorReceiptSource(_evidence())

    batch = MuHip3BreakoutShadowCollector(pressure_source=source)(
        bars,
        symbol="xyz:MU",
        observed_at=pd.Timestamp("2026-08-09T22:00:01Z"),
        cursor=_cursor(long_raw=True, short_raw=False),
    )

    assert len(source.calls) == 1
    assert source.calls[0][1] == int(
        pd.Timestamp("2026-08-09T22:00:00Z").timestamp() * 1_000
    )
    assert batch.decisions[0].side is None
    assert batch.decisions[0].eligible is False


def _ledger_book(
    exchange_ts_ms: int,
    recv_ts_ms: int,
    *,
    bid_size: float,
    ask_size: float,
) -> dict[str, object]:
    return {
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": exchange_ts_ms,
        "recv_ts_ms": recv_ts_ms,
        "bids": [
            {"price": 99.9 - position * 0.1, "size": bid_size} for position in range(10)
        ],
        "asks": [
            {"price": 100.1 + position * 0.1, "size": ask_size}
            for position in range(10)
        ],
    }


def _ledger_source(
    tmp_path: Path,
    books: tuple[dict[str, object], ...],
) -> MuHip3LedgerPreclosePressureSource:
    asset = tmp_path / "xyz:mu.jsonl"
    rows = (
        {
            "event_type": "book_observation",
            "profile_id": "mu_breakout_shadow_xyz:mu",
            "payload": book,
        }
        for book in books
    )
    asset.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("", encoding="utf-8")
    return MuHip3LedgerPreclosePressureSource(
        asset_binding=MuAssetLedgerBinding(
            "xyz:MU",
            asset,
            "mu_breakout_shadow_xyz:mu",
        ),
        cohort_ledger=cohort,
    )


def test_delayed_ledger_receipt_cannot_rewrite_prior_raw_state(
    tmp_path: Path,
) -> None:
    prior_close = int(pd.Timestamp("2026-08-09T21:45:00Z").timestamp() * 1_000)
    current_close = int(pd.Timestamp("2026-08-09T22:00:00Z").timestamp() * 1_000)
    source = _ledger_source(
        tmp_path,
        (
            _ledger_book(
                prior_close - 901_000, prior_close - 901_000, bid_size=3, ask_size=1
            ),
            _ledger_book(
                prior_close - 10_000, prior_close - 9_900, bid_size=3, ask_size=1
            ),
            _ledger_book(
                prior_close - 2_000, prior_close - 1_900, bid_size=3, ask_size=1
            ),
            _ledger_book(
                prior_close - 1_000, prior_close + 2_000, bid_size=1, ask_size=3
            ),
            _ledger_book(
                current_close - 10_000, current_close - 9_900, bid_size=3, ask_size=1
            ),
            _ledger_book(
                current_close - 1_000, current_close - 900, bid_size=3, ask_size=1
            ),
        ),
    )
    bars = _bars()
    bars["open"] = [100.0 + position for position in range(len(bars))]
    bars["close"] = bars["open"]
    bars["high"] = bars["open"] + 0.1
    bars["low"] = bars["open"] - 0.1
    collector = MuHip3BreakoutShadowCollector(pressure_source=source)

    prior = collector(
        bars,
        symbol="xyz:MU",
        observed_at=pd.Timestamp("2026-08-09T21:45:01Z"),
        cursor=_cursor(
            pd.Timestamp("2026-08-09T21:30:00Z"),
            long_raw=True,
            short_raw=False,
        ),
    )
    current = collector(
        bars,
        symbol="xyz:MU",
        observed_at=pd.Timestamp("2026-08-09T22:00:01Z"),
        cursor=prior.next_cursor,
    )

    assert prior.next_cursor.pressure is not None
    assert prior.next_cursor.pressure.imbalance_10 == pytest.approx(0.5)
    assert prior.next_cursor.long_raw is True
    assert current.decisions[0].side is None
    assert current.decisions[0].eligible is False


def test_shadow_identity_is_not_registered_in_current_v25_factories() -> None:
    assert HIP3_STRATEGIES == frozenset(
        {
            HIP3_SWING_INDEX_STRATEGY,
            HIP3_BREAKOUT_INDEX_STRATEGY,
            HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
            HIP3_SWING_COMMODITY_STRATEGY,
            HIP3_BREAKOUT_COMMODITY_STRATEGY,
            HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
        }
    )
    assert MU_SHADOW_PROVIDER_ID not in HIP3_STRATEGIES
    assert MU_SHADOW_PROFILE_ID not in HIP3_STRATEGIES
