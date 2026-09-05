"""Authenticated eight-asset return overlap for continuous V58 research."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_return_context import (
    load_v58_return_context,
    return_context_payload,
)

_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
_PROFILE = "profile"
_RUN_ID = "bidirectional-observe-1787127644202"
_START = 1_787_127_660_000


def test_loader_excludes_warmup_and_freezes_complete_prefix(tmp_path: Path) -> None:
    """Only fully post-activation common bars may describe co-movement."""
    observer, ledger = _observer(tmp_path)

    before = return_context_payload(load_v58_return_context(observer=observer))
    ledger.write_bytes(ledger.read_bytes() + _line(_future_candles()))
    after = return_context_payload(load_v58_return_context(observer=observer))

    assert after == before
    assert before["prospective_start_utc"] == "2026-08-19T08:21:00+00:00"
    assert before["common_completed_bars"] == 19
    assert before["one_minute_return_observations"] == 18
    assert before["five_minute_return_observations"] == 2
    assert len(before["one_minute_pairwise_correlations"]) == 28
    assert len(before["five_minute_pairwise_correlations"]) == 28
    assert before["historical_warmup_bars_excluded"] == 8
    assert before["return_definition"] == "consecutive_completed_close_log_return"
    assert before["stable_covariance_claim"] is False
    assert before["sizing_input"] is False
    assert before["execution_authority"] == "none"


def test_loader_rejects_rows_from_another_profile_fingerprint(tmp_path: Path) -> None:
    """A same-run row cannot borrow candles from another profile identity."""
    observer, ledger = _observer(tmp_path)
    identity, candles = _identity(), _candles()
    identity["profile_fingerprint"] = "wrong-profile"
    candles["profile_fingerprint"] = "wrong-profile"
    changed = _line(identity) + _line(candles)
    ledger.write_bytes(changed)
    evidence = observer.evidence["observer_ledger"]
    assert isinstance(evidence, dict)
    evidence["stable_bytes"] = len(changed)
    evidence["sha256"] = sha256(changed).hexdigest()

    with pytest.raises(ValueError, match="profile fingerprint is invalid"):
        load_v58_return_context(observer=observer)


def test_loader_accepts_equivalent_restart_identity_restatement(tmp_path: Path) -> None:
    """A report-only annotation change cannot move the activation boundary."""
    observer, ledger = _observer(tmp_path)
    before = return_context_payload(load_v58_return_context(observer=observer))
    restart = _identity()
    restart["observed_at_utc"] = "2026-08-19T08:39:45+00:00"
    restart_payload = restart["payload"]
    assert isinstance(restart_payload, dict)
    restart_payload["strategy_evidence"] = {"status": "refreshed"}
    _append_authenticated(observer, ledger, restart)

    after = return_context_payload(load_v58_return_context(observer=observer))

    assert after == before


def test_loader_rejects_restart_identity_execution_drift(tmp_path: Path) -> None:
    """A restart cannot silently change the enabled V58 asset contract."""
    observer, ledger = _observer(tmp_path)
    restart = _identity()
    restart["observed_at_utc"] = "2026-08-19T08:39:45+00:00"
    restart_payload = restart["payload"]
    assert isinstance(restart_payload, dict)
    restart_payload["enabled_symbols"] = list(_SYMBOLS[:-1])
    _append_authenticated(observer, ledger, restart)

    with pytest.raises(ValueError, match="conflicting configuration identity"):
        load_v58_return_context(observer=observer)


def _observer(tmp_path: Path) -> tuple[SuccessorObserverEvidence, Path]:
    ledger = tmp_path / "decisions.jsonl"
    prefix = _line(_identity()) + _line(_candles())
    ledger.write_bytes(prefix)
    status = {
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_id": _RUN_ID,
        "freshness_status": "fresh",
        "technical_complete": True,
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    evidence = {
        "observer_ledger": {
            "path": str(ledger.resolve()),
            "stable_bytes": len(prefix),
            "sha256": sha256(prefix).hexdigest(),
        }
    }
    return SuccessorObserverEvidence(status, evidence), ledger


def _append_authenticated(
    observer: SuccessorObserverEvidence, ledger: Path, row: dict[str, object]
) -> None:
    prefix = ledger.read_bytes() + _line(row)
    ledger.write_bytes(prefix)
    evidence = observer.evidence["observer_ledger"]
    assert isinstance(evidence, dict)
    evidence["stable_bytes"] = len(prefix)
    evidence["sha256"] = sha256(prefix).hexdigest()


def _identity() -> dict[str, object]:
    return _envelope(
        "configuration_identity",
        "2026-08-19T08:20:45.562891+00:00",
        {"enabled_symbols": list(_SYMBOLS)},
    )


def _candles() -> dict[str, object]:
    bars = {
        symbol: [_bar(symbol, offset) for offset in range(-1, 19)]
        for symbol in _SYMBOLS
    }
    return _envelope(
        "market_candles",
        "2026-08-19T08:40:05+00:00",
        {"timeframe": "1m", "bars": bars},
    )


def _future_candles() -> dict[str, object]:
    bars = {symbol: [_bar(symbol, 19)] for symbol in _SYMBOLS}
    return _envelope(
        "market_candles",
        "2026-08-19T08:41:05+00:00",
        {"timeframe": "1m", "bars": bars},
    )


def _bar(symbol: str, offset: int) -> dict[str, object]:
    index = _SYMBOLS.index(symbol)
    close = 100.0 + index * 20.0 + offset * (index + 1) * 0.1
    return {
        "timestamp_ms": _START + offset * 60_000,
        "open": close - 0.02,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "volume": 1.0 + index,
    }


def _envelope(
    event_type: str, observed_at: str, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": observed_at,
        "execution_authority": "none",
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_id": _RUN_ID,
        "payload": payload,
    }


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
