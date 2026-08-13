"""Prospective execution-adapter tests for repaired HIP-3 index decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    Hip3Fresh15JournalCollector,
)

_OPEN = pd.Timestamp("2026-08-13T04:00:00Z")
_CLOSE_MS = int((_OPEN + pd.Timedelta(minutes=15)).timestamp() * 1_000)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [_OPEN],
            "open": [7_700.0],
            "high": [7_710.0],
            "low": [7_695.0],
            "close": [7_705.0],
            "volume": [100.0],
        }
    )


def _decision(symbol: str, *, eligible: bool = True) -> dict[str, object]:
    token = symbol.removeprefix("xyz:").lower()
    side = "long" if eligible else None
    profile = f"{token}_fresh15_pressure_shadow_research_v3"
    decision = {
        "provider_id": HIP3_INDEX_FRESH15_V3_STRATEGY,
        "profile_id": profile,
        "symbol": symbol,
        "decision_time_ms": _CLOSE_MS,
        "side": side,
        "eligible": eligible,
        "decision_imbalance_10": 0.25,
        "pressure_fresh": True,
        "pressure_status": "fresh",
        "pressure_source": "hyperliquid_mainnet_l2_rest",
        "pressure_scan_complete": True,
        "pressure_exchange_ts_ms": _CLOSE_MS - 2_000,
        "pressure_recv_ts_ms": _CLOSE_MS - 1_500,
        "pressure_snapshot_count": 160,
        "pressure_end_boundary_age_ms": 2_000,
        "observed_at_ms": _CLOSE_MS + 3_000,
        "decision_delay_ms": 3_000,
        "prior_decision_boundary_ms": _CLOSE_MS - 900_000,
        "prospective": True,
        "pressure_state_history_complete": True,
        "execution_authority": "none",
    }
    return {
        "schema_version": 1,
        "event_type": f"{token}_hip3_breakout_shadow_decision",
        "event_id": f"{HIP3_INDEX_FRESH15_V3_STRATEGY}|{symbol}|{_CLOSE_MS}",
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": decision,
    }


def _journal(path: Path, *rows: dict[str, object]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _collector(path: Path) -> Hip3Fresh15JournalCollector:
    return Hip3Fresh15JournalCollector(journals={"xyz:SP500": path})


def _observer_state(
    tmp_path: Path,
    *,
    observed_at_ms: int,
    cursor_boundary_ms: int = _CLOSE_MS,
) -> tuple[Path, Path]:
    status = tmp_path / "sp500_latest.json"
    cursor = tmp_path / "sp500_cursor.json"
    status.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "sp500_hip3_breakout_shadow_observer",
                "symbol": "xyz:SP500",
                "provider_id": HIP3_INDEX_FRESH15_V3_STRATEGY,
                "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
                "execution_authority": "none",
                "report_only": True,
                "signing_client_constructed": False,
                "orders_supported": False,
                "runtime_strategy_changed": False,
                "signal_ohlc_source": "hyperliquid_public_candleSnapshot_15m",
                "pressure_source": "hyperliquid_mainnet_l2_rest",
                "observed_at_ms": observed_at_ms,
                "cursor_decision_time_ms": _CLOSE_MS,
            }
        ),
        encoding="utf-8",
    )
    cursor.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "sp500_hip3_breakout_shadow_cursor",
                "symbol": "xyz:SP500",
                "provider_id": HIP3_INDEX_FRESH15_V3_STRATEGY,
                "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
                "execution_authority": "none",
                "report_only": True,
                "decision_time_ms": cursor_boundary_ms,
                "bar_open_ms": cursor_boundary_ms - 900_000,
            }
        ),
        encoding="utf-8",
    )
    return status, cursor


def test_eligible_prospective_decision_becomes_one_attributed_intent(
    tmp_path: Path,
) -> None:
    """A validated v3 journal row may enter once using the matching bar close."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))

    batch = _collector(path)(
        _bars(),
        symbol="xyz:SP500",
        observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
        after_decision_time_ms=_CLOSE_MS - 1,
    )

    assert batch.latest_decision_time_ms == _CLOSE_MS
    assert len(batch.intents) == 1
    assert batch.intents[0].strategy_id == HIP3_INDEX_FRESH15_V3_STRATEGY
    assert batch.intents[0].side == "long"
    assert batch.intents[0].reference_price == pytest.approx(7_705.0)
    assert batch.evaluations[0].eligible is True
    assert batch.evaluations[0].readiness.metrics["pressure_snapshot_count"] == 160
    assert batch.evaluations[0].readiness.metrics["imbalance_10"] == pytest.approx(0.25)
    assert batch.evaluations[0].readiness.metrics["pressure_age_seconds"] == (
        pytest.approx(2.0)
    )
    assert batch.evaluations[0].readiness.metrics["pressure_status"] == "available"


def test_restart_boundary_prevents_historical_replay(tmp_path: Path) -> None:
    """A previously consumed journal row cannot create another live intent."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))

    batch = _collector(path)(
        _bars(),
        symbol="xyz:SP500",
        observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
        after_decision_time_ms=_CLOSE_MS,
    )

    assert batch.latest_decision_time_ms == _CLOSE_MS
    assert batch.intents == ()
    assert batch.evaluations == ()


def test_stale_observer_status_fails_before_live_intent(tmp_path: Path) -> None:
    """A stopped journal writer cannot remain silently live-executable."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))
    observed_at_ms = _CLOSE_MS + 40_000
    state = _observer_state(tmp_path, observed_at_ms=_CLOSE_MS + 3_000)
    collector = Hip3Fresh15JournalCollector(
        journals={"xyz:SP500": path},
        observer_states={"xyz:SP500": state},
        health_now_fn=lambda: pd.Timestamp(observed_at_ms, unit="ms", tz="UTC"),
    )

    with pytest.raises(ValueError, match="observer status is stale"):
        collector(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(observed_at_ms, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )


def test_health_clock_accepts_status_refreshed_during_slow_market_fetch(
    tmp_path: Path,
) -> None:
    """Observer health uses read time while decisions retain the poll cutoff."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))
    poll_started_ms = _CLOSE_MS + 10_000
    status_refreshed_ms = poll_started_ms + 12_000
    health_checked_ms = status_refreshed_ms + 1_000
    state = _observer_state(tmp_path, observed_at_ms=status_refreshed_ms)
    collector = Hip3Fresh15JournalCollector(
        journals={"xyz:SP500": path},
        observer_states={"xyz:SP500": state},
        health_now_fn=lambda: pd.Timestamp(health_checked_ms, unit="ms", tz="UTC"),
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=pd.Timestamp(poll_started_ms, unit="ms", tz="UTC"),
        after_decision_time_ms=_CLOSE_MS - 1,
    )

    assert len(batch.intents) == 1
    assert batch.latest_decision_time_ms == _CLOSE_MS


def test_observer_status_cursor_and_journal_must_share_boundary(
    tmp_path: Path,
) -> None:
    """A mixed observer checkpoint cannot authorize a live journal decision."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))
    observed_at_ms = _CLOSE_MS + 10_000
    state = _observer_state(
        tmp_path,
        observed_at_ms=_CLOSE_MS + 3_000,
        cursor_boundary_ms=_CLOSE_MS - 900_000,
    )
    collector = Hip3Fresh15JournalCollector(
        journals={"xyz:SP500": path},
        observer_states={"xyz:SP500": state},
        health_now_fn=lambda: pd.Timestamp(observed_at_ms, unit="ms", tz="UTC"),
    )

    with pytest.raises(ValueError, match="observer boundaries disagree"):
        collector(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(observed_at_ms, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )


def test_observer_state_identity_must_match_live_route(tmp_path: Path) -> None:
    """A journal cannot borrow a fresh heartbeat from another observer."""
    path = tmp_path / "sp500.jsonl"
    _journal(path, _decision("xyz:SP500"))
    observed_at_ms = _CLOSE_MS + 10_000
    status, cursor = _observer_state(
        tmp_path,
        observed_at_ms=_CLOSE_MS + 3_000,
    )
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["symbol"] = "xyz:SPCX"
    status.write_text(json.dumps(payload), encoding="utf-8")
    collector = Hip3Fresh15JournalCollector(
        journals={"xyz:SP500": path},
        observer_states={"xyz:SP500": (status, cursor)},
    )

    with pytest.raises(ValueError, match="observer identity is invalid"):
        collector(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(observed_at_ms, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )


def test_missing_journal_decision_does_not_advance_past_it(tmp_path: Path) -> None:
    """The router waits for the prospective writer instead of losing the bar."""
    path = tmp_path / "sp500.jsonl"
    path.write_text("", encoding="utf-8")
    prior = _CLOSE_MS - 1

    batch = _collector(path)(
        _bars(),
        symbol="xyz:SP500",
        observed_at=pd.Timestamp(_CLOSE_MS + 1_000, unit="ms", tz="UTC"),
        after_decision_time_ms=prior,
    )

    assert batch.latest_decision_time_ms == prior
    assert batch.intents == ()


def test_success_shaped_malformed_decision_fails_closed(tmp_path: Path) -> None:
    """Eligibility cannot contradict pressure freshness or execution authority."""
    path = tmp_path / "sp500.jsonl"
    row = _decision("xyz:SP500")
    row["decision"]["pressure_fresh"] = False
    _journal(path, row)

    with pytest.raises(ValueError, match="eligible decision contract"):
        _collector(path)(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )


def test_duplicate_event_identity_fails_closed(tmp_path: Path) -> None:
    """Duplicate prospective decisions cannot alias one live entry boundary."""
    path = tmp_path / "sp500.jsonl"
    row = _decision("xyz:SP500")
    _journal(path, row, row)

    with pytest.raises(ValueError, match="duplicate event"):
        _collector(path)(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pressure_source", "other_venue", "pressure source"),
        ("pressure_exchange_ts_ms", _CLOSE_MS + 1, "pressure timestamps"),
        ("pressure_recv_ts_ms", _CLOSE_MS + 3_001, "pressure timestamps"),
    ],
)
def test_pressure_provenance_must_be_exact(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    """Success-shaped evidence cannot hide a wrong source or impossible time."""
    path = tmp_path / "sp500.jsonl"
    row = _decision("xyz:SP500")
    row["decision"][field] = value
    _journal(path, row)

    with pytest.raises(ValueError, match=message):
        _collector(path)(
            _bars(),
            symbol="xyz:SP500",
            observed_at=pd.Timestamp(_CLOSE_MS + 10_000, unit="ms", tz="UTC"),
            after_decision_time_ms=_CLOSE_MS - 1,
        )
