"""Fail-closed local operator command inbox tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_operator_commands import (
    CohortOperatorInbox,
    operator_command_maximum_age_seconds,
)

_NOW = datetime(2026, 8, 2, 15, tzinfo=UTC)
_RUN = "bidirectional-live-1785682800000"
_PROFILE = "a" * 64


def _write(root: Path, request_id: str, **updates: object) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "request_id": request_id,
        "run_id": _RUN,
        "profile_fingerprint": _PROFILE,
        "created_at_utc": _NOW.isoformat(),
        "action": "manual_enter",
        "symbol": "BTC",
        "provider": "hulk_expansion_bidirectional_tuned_v2",
        "side": "long",
        "settings": None,
    }
    payload.update(updates)
    pending = root / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / f"{request_id}.json").write_text(json.dumps(payload))


def test_claim_validates_identity_and_moves_completed_request(tmp_path: Path) -> None:
    """A matching fresh request has one durable lifecycle across directories."""
    request_id = "1" * 32
    _write(tmp_path, request_id)
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    claims = inbox.claim_pending()

    assert len(claims) == 1
    assert claims[0].command is not None
    assert claims[0].issue is None
    assert not (tmp_path / "pending" / f"{request_id}.json").exists()
    assert (tmp_path / "claimed" / f"{request_id}.json").exists()

    inbox.finalize(claims[0], status="completed", reason="venue_reconciled")

    assert (tmp_path / "completed" / f"{request_id}.json").exists()
    outcome = json.loads((tmp_path / "outcomes" / f"{request_id}.json").read_text())
    assert outcome["status"] == "completed"
    assert outcome["reason"] == "venue_reconciled"


def test_wrong_run_stale_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    """A request cannot cross a run, outlive its TTL, or smuggle extra data."""
    _write(tmp_path, "2" * 32, run_id="wrong")
    _write(
        tmp_path,
        "3" * 32,
        created_at_utc=(_NOW - timedelta(minutes=2)).isoformat(),
    )
    _write(tmp_path, "4" * 32, private_key="forbidden")
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    claims = inbox.claim_pending()

    assert [claim.command for claim in claims] == [None, None, None]
    reasons = [claim.issue for claim in claims]
    assert reasons == [
        "request run_id does not match active backend",
        "request is stale",
        "request fields do not match the command schema",
    ]
    for claim in claims:
        inbox.finalize(claim, status="rejected", reason=claim.issue or "invalid")
        assert (tmp_path / "rejected" / f"{claim.request_id}.json").exists()


def test_manual_close_requires_null_provider_and_side(tmp_path: Path) -> None:
    """Close requests cannot disguise a directional opening instruction."""
    request_id = "5" * 32
    _write(
        tmp_path,
        request_id,
        action="manual_close",
        provider=None,
        side=None,
    )
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    claim = inbox.claim_pending()[0]

    assert claim.command is not None
    assert claim.command.action == "manual_close"


def test_manual_close_accepts_canonical_hip3_symbol(tmp_path: Path) -> None:
    """A HIP-3 close retains the exact xyz namespace used by live engines."""
    request_id = "a" * 32
    _write(
        tmp_path,
        request_id,
        action="manual_close",
        symbol="xyz:BRENTOIL",
        provider=None,
        side=None,
    )
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    claim = inbox.claim_pending()[0]

    assert claim.issue is None
    assert claim.command is not None
    assert claim.command.symbol == "xyz:BRENTOIL"


def test_transition_drain_requires_portfolio_scope_and_no_trade_fields(
    tmp_path: Path,
) -> None:
    """A drain is an identity-bound portfolio control, not a disguised trade."""
    request_id = "6" * 32
    _write(
        tmp_path,
        request_id,
        action="transition_drain",
        symbol="MULTI",
        provider=None,
        side=None,
    )
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    claim = inbox.claim_pending()[0]

    assert claim.issue is None
    assert claim.command is not None
    assert claim.command.action == "transition_drain"
    assert claim.command.symbol == "MULTI"


def test_cohort_command_age_budget_covers_delayed_cycle_and_remains_finite(
    tmp_path: Path,
) -> None:
    """Nine-asset commands survive a healthy cycle but expire after its budget."""
    budget = operator_command_maximum_age_seconds(
        poll_seconds=15.0,
        symbol_count=9,
    )
    accepted_id = "7" * 32
    rejected_id = "8" * 32
    _write(
        tmp_path,
        accepted_id,
        created_at_utc=(_NOW - timedelta(seconds=90)).isoformat(),
    )
    _write(
        tmp_path,
        rejected_id,
        created_at_utc=(_NOW - timedelta(seconds=121)).isoformat(),
    )
    inbox = CohortOperatorInbox(
        root=tmp_path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
        maximum_age_seconds=budget,
    )

    claims = inbox.claim_pending()

    assert budget == 120.0
    assert claims[0].request_id == accepted_id
    assert claims[0].command is not None
    assert claims[0].issue is None
    assert claims[1].request_id == rejected_id
    assert claims[1].command is None
    assert claims[1].issue == "request is stale"


def test_cohort_command_age_budget_rejects_invalid_runtime_shape() -> None:
    """Invalid cohort timing cannot silently weaken stale-command rejection."""
    with pytest.raises(ValueError, match="poll seconds"):
        operator_command_maximum_age_seconds(
            poll_seconds=0.0,
            symbol_count=9,
        )
    with pytest.raises(ValueError, match="symbol count"):
        operator_command_maximum_age_seconds(
            poll_seconds=15.0,
            symbol_count=0,
        )
