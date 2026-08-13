"""Tests for the prospective asymmetric shared-portfolio observer."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_asymmetric_forward_observer import (
    build_asymmetric_forward_observer,
)

_PROFILE = "v25-profile-fingerprint"
_RUN_ID = "v25-live-run"
_CUTOFF_MS = 1_000_000


def test_observer_separates_candidate_from_excluded_symmetric_sides() -> None:
    """Post-cutoff exact sides must not be pooled with symmetric exclusions."""
    trades = [
        _trade("HYPE", "hype_breakout_onset_bidirectional_v1", "long", 1.0, 0),
        _trade("SOL", "range_onset_bidirectional_v1", "short", -0.5, 1),
        _trade("HYPE", "hype_breakout_onset_bidirectional_v1", "short", -1.0, 2),
        _trade(
            "ETH",
            "eth_breakout_precompression_pullback_bidirectional_v1",
            "short",
            0.2,
            3,
        ),
        _trade(
            "HYPE",
            "hype_breakout_onset_bidirectional_v1",
            "long",
            5.0,
            -1,
        ),
        _trade("BTC", "hulk_expansion_bidirectional_tuned_v2", "long", 9.0, 4),
    ]

    report = build_asymmetric_forward_observer(
        trades,
        current_profile_fingerprint=_PROFILE,
        current_run_id=_RUN_ID,
        predeclared_at_utc="1970-01-01T00:16:40Z",
        entry_cutoff_timestamp_ms=_CUTOFF_MS,
    )

    candidate = report["candidate"]
    excluded = report["excluded_symmetric_sides"]
    assert report["contract"]["execution_authority"] == "none"
    assert report["evidence_state"] == "prospective_resolutions_observed"
    assert report["source_counts"] == {
        "candidate_post_cutoff": 2,
        "excluded_symmetric_post_cutoff": 2,
        "pre_cutoff_in_scope": 1,
        "profile_mismatch_in_scope": 0,
        "unrelated": 1,
    }
    assert candidate["closed_trades"] == 2
    assert candidate["net_pnl_usd"] == pytest.approx(0.5)
    assert candidate["profit_factor"] == pytest.approx(2.0)
    assert candidate["net_pnl_excluding_largest_winner_usd"] == pytest.approx(-0.5)
    assert set(candidate["by_route_side"]) == {
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH|long",
        "hype_breakout_onset_bidirectional_v1|HYPE|long",
        "range_onset_bidirectional_v1|SOL|long",
        "range_onset_bidirectional_v1|SOL|short",
    }
    assert excluded["closed_trades"] == 2
    assert excluded["net_pnl_usd"] == pytest.approx(-0.8)


def test_observer_waits_when_no_matching_lifecycle_resolved_after_cutoff() -> None:
    """Pre-cutoff and mismatched-profile trades cannot validate the observer."""
    before = _trade("SOL", "range_onset_bidirectional_v1", "long", 1.0, -1)
    mismatch = _trade(
        "SOL",
        "range_onset_bidirectional_v1",
        "short",
        1.0,
        0,
        profile="different-profile",
    )

    report = build_asymmetric_forward_observer(
        [before, mismatch],
        current_profile_fingerprint=_PROFILE,
        current_run_id=_RUN_ID,
        predeclared_at_utc="1970-01-01T00:16:40Z",
        entry_cutoff_timestamp_ms=_CUTOFF_MS,
    )

    assert report["evidence_state"] == "awaiting_post_cutoff_resolution"
    assert report["candidate"]["closed_trades"] == 0
    assert report["candidate"]["net_pnl_usd"] == 0.0
    assert report["source_counts"]["pre_cutoff_in_scope"] == 1
    assert report["source_counts"]["profile_mismatch_in_scope"] == 1


def test_observer_rejects_an_invalid_completed_lifecycle() -> None:
    """A malformed in-scope trade must fail rather than become missing evidence."""
    trade = _trade("SOL", "range_onset_bidirectional_v1", "long", 1.0, 0)
    trade["exit"] = {"venue_timestamp_ms": _CUTOFF_MS - 1}

    with pytest.raises(ValueError, match="exit must follow entry"):
        build_asymmetric_forward_observer(
            [trade],
            current_profile_fingerprint=_PROFILE,
            current_run_id=_RUN_ID,
            predeclared_at_utc="1970-01-01T00:16:40Z",
            entry_cutoff_timestamp_ms=_CUTOFF_MS,
        )


def _trade(
    symbol: str,
    strategy_id: str,
    side: str,
    net_pnl_usd: float,
    entry_offset_ms: int,
    *,
    profile: str = _PROFILE,
) -> dict[str, object]:
    entry_ms = _CUTOFF_MS + entry_offset_ms
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "source_profile_fingerprint": profile,
        "source_run_id": _RUN_ID,
        "entry": {"venue_timestamp_ms": entry_ms},
        "exit": {"venue_timestamp_ms": entry_ms + 10},
        "fees_usd": 0.1,
        "funding_usd": -0.01,
        "net_pnl_usd": net_pnl_usd,
        "net_return_on_margin_pct": net_pnl_usd * 2.0,
    }
