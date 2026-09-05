"""Exact BTC sweep status normalization for the V58 consolidation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.research.v58_btc_sweep_status import (
    load_v58_btc_sweep_lifecycle_status,
)
from v58_btc_sweep_status_fixtures import btc_sweep_status

_NOW = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)
_RUN = "bidirectional-observe-1787127644202"
_PROFILE = "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"


def test_loads_fresh_exact_report_only_btc_sweep_status(tmp_path: Path) -> None:
    """The canonical report must recognize the frozen V58 watcher identity."""
    path = tmp_path / "btc.json"
    path.write_text(
        json.dumps(btc_sweep_status(_NOW, _RUN, _PROFILE)), encoding="utf-8"
    )

    result = load_v58_btc_sweep_lifecycle_status(
        path,
        observer_run_id=_RUN,
        observer_profile_fingerprint=_PROFILE,
        observed_at=_NOW,
        maximum_age_seconds=180.0,
    )

    assert result.state == "awaiting_resolution"
    assert result.pending == 0
    assert result.resolved == 0
    assert result.technical_complete is True
    assert result.source_age_seconds == 10.0
    assert result.evidence["path"] == str(path.resolve())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("contract", "execution_authority", "live"), "authority or identity"),
        (("contract", "stop_bps", 80.0), "frozen exit contract"),
        (("summary", "selected_non_overlapping", 1), "summary does not reconcile"),
    ],
)
def test_rejects_unsafe_or_internally_inconsistent_status(
    tmp_path: Path, mutation: tuple[str, str, object], message: str
) -> None:
    """Success-shaped watcher drift must fail before canonical publication."""
    payload = btc_sweep_status(_NOW, _RUN, _PROFILE)
    section, field, value = mutation
    payload[section][field] = value
    path = tmp_path / "btc.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_v58_btc_sweep_lifecycle_status(
            path,
            observer_run_id=_RUN,
            observer_profile_fingerprint=_PROFILE,
            observed_at=_NOW,
            maximum_age_seconds=180.0,
        )


def test_rejects_stale_status(tmp_path: Path) -> None:
    """A stopped watcher cannot remain current research evidence."""
    payload = btc_sweep_status(_NOW, _RUN, _PROFILE)
    payload["observed_at_utc"] = (_NOW - timedelta(seconds=181)).isoformat()
    path = tmp_path / "btc.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="stale"):
        load_v58_btc_sweep_lifecycle_status(
            path,
            observer_run_id=_RUN,
            observer_profile_fingerprint=_PROFILE,
            observed_at=_NOW,
            maximum_age_seconds=180.0,
        )
