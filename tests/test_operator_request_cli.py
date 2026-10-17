"""Headless operator requests retain the inbox contract without live clients."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.cohort_operator_commands import CohortOperatorInbox
from hypervector.live.cohort_operator_requests import build_request, publish_request


def test_published_request_is_accepted_by_the_existing_backend(tmp_path: Path) -> None:
    """The new CLI transport must interoperate with the production inbox."""
    now = datetime.now(UTC)
    inbox = CohortOperatorInbox(
        root=tmp_path, run_id="run", profile_fingerprint="profile", now_fn=lambda: now
    )
    request = build_request(
        run_id="run",
        profile_fingerprint="profile",
        action="manual_enter",
        symbol="BTC",
        provider="provider",
        side="long",
        now=now,
    )
    target = publish_request(tmp_path, request, now=now)
    assert target.is_file()
    claims = inbox.claim_pending()
    assert len(claims) == 1
    assert claims[0].issue is None
    assert claims[0].command.action == "manual_enter"


def test_request_publication_requires_an_existing_inbox(tmp_path: Path) -> None:
    """A mistyped path must not create a seemingly active command channel."""
    request = build_request(
        run_id="run",
        profile_fingerprint="profile",
        action="transition_drain",
        symbol="MULTI",
    )
    with pytest.raises(ValueError, match="inbox"):
        publish_request(tmp_path / "missing", request)
    assert not (tmp_path / "missing").exists()


def test_invalid_manual_entry_is_rejected_before_publication() -> None:
    """The composer enforces the same action shape as the consumer."""
    with pytest.raises(ValueError, match="manual entry"):
        build_request(
            run_id="run",
            profile_fingerprint="profile",
            action="manual_enter",
            symbol="BTC",
        )


def test_duplicate_publication_cannot_replace_a_request(tmp_path: Path) -> None:
    """Atomic publication preserves the existing request on ID collision."""
    (tmp_path / "pending").mkdir()
    request = build_request(
        run_id="run", profile_fingerprint="profile", action="manual_close", symbol="BTC"
    )
    target = publish_request(tmp_path, request)
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        publish_request(tmp_path, request)
    assert target.read_bytes() == original


def test_naive_request_clock_is_rejected() -> None:
    """Request freshness needs an unambiguous timezone-aware clock."""
    with pytest.raises(ValueError, match="timezone-aware"):
        build_request(
            run_id="run",
            profile_fingerprint="profile",
            action="manual_close",
            symbol="BTC",
            now=datetime(2026, 1, 1),
        )
