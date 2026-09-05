"""Current-run visible liquidity context for continuous V58 research."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_liquidity_context import (
    liquidity_context_payload,
    load_v58_liquidity_context,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
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


def test_loader_uses_authenticated_books_and_excludes_future_appends(
    tmp_path: Path,
) -> None:
    """Visible completion must use only the checkpoint-authenticated prefix."""
    observer, ledger = _observer(tmp_path)

    before = liquidity_context_payload(
        load_v58_liquidity_context(_CONFIG, observer=observer)
    )
    ledger.write_bytes(ledger.read_bytes() + _line(_books(4)))
    after = liquidity_context_payload(
        load_v58_liquidity_context(_CONFIG, observer=observer)
    )

    assert after == before
    assert before["synchronized_snapshot_count"] == 3
    assert len(before["assets"]) == 8
    assert all(row["both_complete_rate"] == 1.0 for row in before["assets"])
    assert all(row["snapshot_count"] == 3 for row in before["assets"])
    assert before["minimum_both_complete_rate"] == 1.0
    assert before["visible_book_fill_claim"] is False
    assert before["sizing_input"] is False
    assert before["execution_authority"] == "none"


def test_loader_reports_insufficient_visible_depth_without_fill_claim(
    tmp_path: Path,
) -> None:
    """An incomplete book side must remain measurable and fail visible capacity."""
    observer, _ = _observer(tmp_path, thin_symbol="xyz:SNDK")

    payload = liquidity_context_payload(
        load_v58_liquidity_context(_CONFIG, observer=observer)
    )

    sndk = next(row for row in payload["assets"] if row["symbol"] == "xyz:SNDK")
    assert sndk["both_complete_rate"] == 0.0
    assert sndk["bid_visible_cost_bps_p99"] is None
    assert sndk["ask_visible_cost_bps_p99"] is None
    assert payload["visible_book_fill_claim"] is False


def test_loader_rejects_profile_mismatch(tmp_path: Path) -> None:
    """Authenticated rows must retain the observer profile fingerprint."""
    observer, _ = _observer(tmp_path)
    observer.status["profile_fingerprint"] = "different-profile"

    try:
        load_v58_liquidity_context(_CONFIG, observer=observer)
    except ValueError as exc:
        assert "profile fingerprint" in str(exc)
    else:
        raise AssertionError("profile mismatch was accepted")


def _observer(
    tmp_path: Path, *, thin_symbol: str | None = None
) -> tuple[SuccessorObserverEvidence, Path]:
    ledger = tmp_path / "decisions.jsonl"
    prefix = b"".join(
        _line(_books(sequence, thin_symbol=thin_symbol)) for sequence in range(1, 4)
    )
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


def _books(sequence: int, *, thin_symbol: str | None = None) -> dict[str, object]:
    books = {
        symbol: _book(symbol, sequence, thin=symbol == thin_symbol)
        for symbol in _SYMBOLS
    }
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": "market_books",
        "observed_at_utc": f"2026-08-19T11:00:{sequence:02d}+00:00",
        "execution_authority": "none",
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_id": _RUN_ID,
        "payload": {"books": books},
    }


def _book(symbol: str, sequence: int, *, thin: bool = False) -> dict[str, object]:
    index = _SYMBOLS.index(symbol)
    mid = 100.0 + index * 10.0
    exchange = 1_787_138_000_000 + sequence * 1_000
    return {
        "symbol": symbol,
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": exchange,
        "recv_ts_ms": exchange + sequence * 10,
        "mid_px": mid,
        "spread_bps": 0.01 / mid * 10_000.0,
        "bid_depth_ratio": 0.5,
        "opi": 0.0,
        "bids": [{"price": mid - 0.005, "size": 0.001 if thin else 100.0, "orders": 1}],
        "asks": [{"price": mid + 0.005, "size": 0.001 if thin else 100.0, "orders": 1}],
    }


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
