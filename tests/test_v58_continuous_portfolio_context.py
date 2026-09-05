"""Source-bound portfolio opportunity context for the V58 research loop."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_portfolio_context import (
    load_v58_portfolio_context,
    portfolio_context_payload,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")


def test_loader_uses_checkpoint_prefix_and_reports_concurrent_margin(
    tmp_path: Path,
) -> None:
    """Future appends cannot change same-prefix portfolio concentration."""
    observer, ledger = _observer(tmp_path)

    context = load_v58_portfolio_context(_CONFIG, observer=observer)
    before = portfolio_context_payload(context)
    ledger.write_bytes(ledger.read_bytes() + _line(_routing(observer, 2, False)))
    after = portfolio_context_payload(
        load_v58_portfolio_context(_CONFIG, observer=observer)
    )

    assert after == before
    assert before["routing_cycles"] == 1
    assert before["prospective_evaluations"] == 2
    assert before["maximum_concurrent_eligible_symbols"] == 2
    assert before["maximum_concurrent_margin_fraction"] == pytest.approx(0.13)
    assert before["edge_claim"] is False
    assert before["execution_authority"] == "none"


def test_loader_rejects_rewritten_checkpoint_prefix(tmp_path: Path) -> None:
    """Historical concentration cannot be recomputed from mutated bytes."""
    observer, ledger = _observer(tmp_path)
    ledger.write_bytes(_line(_routing(observer, 9, True)))

    with pytest.raises(ValueError, match="hash does not match"):
        load_v58_portfolio_context(_CONFIG, observer=observer)


def _observer(tmp_path: Path) -> tuple[SuccessorObserverEvidence, Path]:
    ledger = tmp_path / "decisions.jsonl"
    base = load_multi_asset_live_config(_CONFIG, mode="observe")
    rebound = with_observer_ledger_root(base, tmp_path)
    run_id = "bidirectional-observe-1787127644202"
    status = {
        "profile_id": rebound.profile_id,
        "profile_fingerprint": rebound.profile_fingerprint,
        "run_id": run_id,
        "freshness_status": "fresh",
        "technical_complete": True,
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    prefix = _line(
        _routing_status(rebound.profile_id, rebound.profile_fingerprint, run_id)
    )
    ledger.write_bytes(prefix)
    evidence = {
        "path": str(ledger.resolve()),
        "sha256": sha256(prefix).hexdigest(),
        "bytes": len(prefix),
        "stable_bytes": len(prefix),
        "source_bytes_observed": len(prefix),
        "dropped_tail_bytes": 0,
        "incomplete_tail_dropped": False,
    }
    return SuccessorObserverEvidence(status, {"observer_ledger": evidence}), ledger


def _routing(
    observer: SuccessorObserverEvidence, sequence: int, eligible: bool
) -> dict[str, object]:
    return _routing_status(
        str(observer.status["profile_id"]),
        str(observer.status["profile_fingerprint"]),
        str(observer.status["run_id"]),
        sequence=sequence,
        eligible=eligible,
    )


def _routing_status(
    profile_id: str,
    fingerprint: str,
    run_id: str,
    *,
    sequence: int = 1,
    eligible: bool = True,
) -> dict[str, object]:
    evaluations = [
        _evaluation(
            "ETH",
            "eth_breakout_precompression_pullback_bidirectional_v1",
            "long",
            eligible,
        )
    ]
    evaluations.append(
        _evaluation(
            "HYPE",
            "hype_breakout_compression_alignment_bidirectional_v2",
            "short",
            eligible,
        )
    )
    return {
        "sequence": sequence,
        "event_type": "intent_routing",
        "observed_at_utc": "2026-08-19T11:00:00+00:00",
        "execution_authority": "none",
        "profile_id": profile_id,
        "profile_fingerprint": fingerprint,
        "run_id": run_id,
        "payload": {"evaluations": evaluations},
    }


def _evaluation(
    symbol: str, strategy: str, side: str, eligible: bool
) -> dict[str, object]:
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "decision_time_ms": 1_787_128_800_000,
        "eligible": eligible,
        "side": side,
        "reason": "ready" if eligible else "waiting",
        "decision_action": f"enter_{side}" if eligible else "hold",
    }


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
