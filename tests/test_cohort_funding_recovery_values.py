"""Identity, legacy-history and invalid-clock coverage for restart funding cursors."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_funding_recovery import (
    initial_funding_cursor,
    recover_funding_cursor,
)
from hypervector.live.cohort_funding_window import (
    committed_funding_window,
    funding_window_from_payload,
)
from hypervector.live.asset_ledger import AssetLiveLedger

DAY_MS = 86_400_000


def ledger(tmp_path: Path, fingerprint: str = "owned") -> AssetLiveLedger:
    """Create a local ledger using the actual persistence validator."""
    return AssetLiveLedger(
        path=tmp_path / "live/bidirectional_cohort/decisions.jsonl",
        profile_id="test",
        profile_fingerprint=fingerprint,
        run_fingerprint="run",
        run_id="prior",
    )


def append(
    source: AssetLiveLedger, event: str, payload: dict[str, object], clock: int = 1_000
) -> None:
    """Append one explicitly timed source record without a network boundary."""
    source.append(
        event_type=event,
        observed_at_utc=datetime.fromtimestamp(clock / 1_000, UTC).isoformat(),
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload=payload,
    )


def test_new_and_foreign_profile_history_do_not_supply_an_owned_cursor(
    tmp_path: Path,
) -> None:
    """A missing cursor retains default overlap and cannot borrow another profile."""
    source = ledger(tmp_path, "foreign")
    assert recover_funding_cursor(source, "owned") is None
    append(
        source,
        "funding_reconciliation_window",
        committed_funding_window(1, 2, 3, 0).as_payload(),
    )
    assert recover_funding_cursor(source, "owned") is None
    assert initial_funding_cursor(2 * DAY_MS, None) == DAY_MS


def test_legacy_profile_without_a_window_uses_its_first_activation(
    tmp_path: Path,
) -> None:
    """An interruption before the first cursor commit preserves the earlier boundary."""
    source = ledger(tmp_path)
    append(source, "configuration_identity", {}, 1_000)
    append(source, "configuration_identity", {}, 2_000)
    assert recover_funding_cursor(source, "owned") == 1_000


def test_latest_valid_window_is_used_and_malformed_latest_window_refuses(
    tmp_path: Path,
) -> None:
    """Corrupted recent evidence cannot silently fall back to an earlier cursor."""
    source = ledger(tmp_path)
    append(
        source,
        "funding_reconciliation_window",
        committed_funding_window(1, 2, 3, 0).as_payload(),
    )
    append(
        source,
        "funding_reconciliation_window",
        committed_funding_window(2, 4, 5, 1).as_payload(),
    )
    assert recover_funding_cursor(source, "owned") == 5
    append(source, "funding_reconciliation_window", {})
    with pytest.raises(ValueError, match="boundary semantics"):
        recover_funding_cursor(source, "owned")


@pytest.mark.parametrize(
    ("activation", "prior", "expected"),
    [
        (1_000, None, 0),
        (2 * DAY_MS, DAY_MS + 1, DAY_MS),
        (2 * DAY_MS, 1, 1),
        (2 * DAY_MS, 0, 0),
    ],
)
def test_valid_recovery_retains_overlap_without_skipping_downtime(
    activation: int, prior: int | None, expected: int
) -> None:
    """Use the earlier of the saved boundary and existing default lookback."""
    assert initial_funding_cursor(activation, prior) == expected


@pytest.mark.parametrize(
    ("activation", "prior"),
    [(-1, None), (True, None), (1.5, None), (1_000, -1), (1_000, True), (1_000, 1_001)],
)
def test_invalid_or_future_funding_clocks_refuse(
    activation: object, prior: object
) -> None:
    """Bad clocks cannot create a success-shaped funding coverage result."""
    with pytest.raises(ValueError):
        initial_funding_cursor(activation, prior)


@pytest.mark.parametrize(
    "change",
    [
        {"action_count": True},
        {"post_action_reconciliation": 1},
        {"funding_start_time_ms": "1"},
        {"boundary_semantics": "exclusive"},
    ],
)
def test_durable_window_codec_rejects_malformed_fields(
    change: dict[str, object],
) -> None:
    """Recovery and audit apply the same typed cursor evidence contract."""
    payload = committed_funding_window(1, 2, 3, 0).as_payload()
    with pytest.raises(ValueError):
        funding_window_from_payload(payload | change)


def test_durable_window_codec_rejects_non_object_and_roundtrips_valid_window() -> None:
    """Decode only explicit compatible evidence objects."""
    window = committed_funding_window(1, 2, 3, 1)
    assert funding_window_from_payload(window.as_payload()) == window
    with pytest.raises(ValueError, match="object"):
        funding_window_from_payload(None)


@pytest.mark.parametrize("timestamp", [None, "2026-09-11T15:00:00"])
def test_legacy_activation_requires_an_explicit_aware_timestamp(
    tmp_path: Path, timestamp: object
) -> None:
    """A malformed source timestamp cannot become a guessed funding boundary."""
    source = ledger(tmp_path)
    source.path.parent.mkdir(parents=True)
    source.path.write_text(
        json.dumps(
            {
                "sequence": 1,
                "profile_fingerprint": "owned",
                "event_type": "configuration_identity",
                "observed_at_utc": timestamp,
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="timestamp|timezone"):
        recover_funding_cursor(source, "owned")
