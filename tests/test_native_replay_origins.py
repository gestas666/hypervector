"""Native durable intent clocks must survive the bridge to exact replay economics."""

from pathlib import Path

import pytest

from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_origins import NativeReplayOrigins


def origin(tmp_path: Path) -> tuple[NativeReplayOrigins, SolLiveLedger]:
    """Use a real native ledger with explicit offline identity and one known clock."""
    ledger = SolLiveLedger(
        path=tmp_path / "live/bidirectional_cohort/ccc.jsonl",
        profile_id="offline",
        profile_fingerprint="profile",
        run_fingerprint="run",
        run_id="origin-test",
    )
    return NativeReplayOrigins(ReplayClock(2000), {"xyz:CCC": ledger}), ledger


def append(ledger: SolLiveLedger, event: str, payload: dict[str, object]) -> None:
    """Write the same timestamped durable shape consumed by the real order bridge."""
    ledger.append(
        event_type=event,
        observed_at_utc="1970-01-01T00:00:01.500+00:00",
        live_armed=False,
        execution_authority="none",
        payload=payload,
    )


def test_explicit_entry_deadline_origin_takes_precedence_over_other_decision(
    tmp_path: Path,
) -> None:
    """Use the submitted deadline's original clock and consume one native intent only once."""
    reader, ledger = origin(tmp_path)
    append(ledger, "regime_decision", {"decision_time_ms": 1000})
    append(
        ledger, "order_intent", {"operation": "entry", "entry_deadline": {"decision_time_ms": 1200}}
    )
    assert reader("xyz:CCC", False) == 1200
    with pytest.raises(ValueError, match="durable native order intent"):
        reader("xyz:CCC", False)
    append(ledger, "order_intent", {"operation": "reduce_only_close"})
    assert reader("xyz:CCC", True) == 1500


@pytest.mark.parametrize("clock", [None, True, 2001])
def test_missing_malformed_or_future_entry_origin_cannot_be_invented(
    tmp_path: Path, clock: object
) -> None:
    """A dispatch timestamp is not a fallback for missing native entry provenance."""
    reader, ledger = origin(tmp_path)
    if clock is not None:
        append(ledger, "regime_decision", {"decision_time_ms": clock})
    append(ledger, "order_intent", {"operation": "entry"})
    with pytest.raises(ValueError):
        reader("xyz:CCC", False)
