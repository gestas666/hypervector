"""Validation contract for the source-follow shadow-only runtime profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
)
from hypervector.paper.runner import _requires_fresh_warmup
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
    load_source_follow_profile,
)
from hypervector.strategies.runtime_profile import load_hypervelocity_runtime_profile


PROFILE = Path("configs/hypervelocity_source_follow_shadow.toml")
LEAD_PROFILE = Path("configs/hypervelocity_source_follow_minrange12_shadow.toml")
ALLOC35_PROFILE = Path(
    "configs/hypervelocity_source_follow_minrange12_alloc35_shadow.toml"
)
SESSION_ALLOC35_PROFILE = Path(
    "configs/hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow.toml"
)
BIDIRECTIONAL_PROFILE = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow.toml"
)
MEASURED_PROFILE = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
)


@pytest.mark.integration
def test_source_follow_profile_is_distinct_and_exactly_pinned() -> None:
    """The measured candidate cannot silently mutate the faithful baseline."""
    profile = load_source_follow_profile(PROFILE)
    faithful = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")

    assert isinstance(profile, SourceFollowHypervelocityProfile)
    assert profile.profile_id == "hypervelocity_source_follow_shadow_v1"
    assert profile.direction_mode == "source_follow_short"
    assert profile.margin_fraction == pytest.approx(0.50)
    assert profile.leverage == pytest.approx(30.0)
    assert profile.margin_fraction * profile.leverage == pytest.approx(15.0)
    assert profile.target_margin_pct == pytest.approx(8.0)
    assert profile.entry_ttl_seconds == pytest.approx(60.0)
    assert profile.maximum_hold_seconds == pytest.approx(86_400.0)
    assert profile.minimum_confidence == pytest.approx(0.70)
    assert profile.minimum_range_bps == pytest.approx(0.0)
    assert profile.maximum_range_bps == pytest.approx(100.0)
    assert profile.entry_pulse_seconds == pytest.approx(60.0)
    assert profile.source_revision == "ad15f2bdc949619be495a5f516babd08f7f52a90"
    assert profile.source_backend_root.is_dir()
    assert profile.runtime_mode == "shadow"
    assert profile.metalabel_mode == "observe"
    assert faithful.margin_fraction == pytest.approx(0.70)
    assert faithful.entry_ttl_seconds == pytest.approx(300.0)


@pytest.mark.integration
def test_source_follow_profile_reports_the_causal_regime_contract() -> None:
    """Telemetry exposes the source policy actually controlling entry."""
    policy = load_source_follow_profile(PROFILE).regime_policy()

    assert policy["engine"] == "pinned_hypertrader_source_follow_v1"
    assert policy["source_revision"] == ("ad15f2bdc949619be495a5f516babd08f7f52a90")
    assert policy["entry_trigger"] == "confirmed_5m_trend_down_primary_onset"
    assert policy["decision_delay_seconds"] == pytest.approx(300.0)
    assert policy["entry_pulse_seconds"] == pytest.approx(60.0)
    assert policy["minimum_confidence"] == pytest.approx(0.70)
    assert policy["minimum_completed_5m_range_bps"] == pytest.approx(0.0)
    assert policy["maximum_completed_5m_range_bps"] == pytest.approx(100.0)
    assert policy["session"] == "24/7"
    assert policy["side"] == "short"


@pytest.mark.integration
def test_minrange12_lead_is_a_distinct_shadow_profile() -> None:
    """The development lead must not mutate the frozen source-follow control."""
    lead = load_source_follow_profile(LEAD_PROFILE)
    control = load_source_follow_profile(PROFILE)

    assert lead.profile_id == "hypervelocity_source_follow_minrange12_shadow_v1"
    assert lead.minimum_range_bps == pytest.approx(12.0)
    assert lead.maximum_range_bps == pytest.approx(100.0)
    assert lead.runtime_mode == "shadow"
    assert lead.metalabel_mode == "observe"
    assert lead.regime_policy()["minimum_completed_5m_range_bps"] == 12.0
    assert control.minimum_range_bps == 0.0


@pytest.mark.integration
def test_runtime_dispatch_loads_the_minrange12_profile() -> None:
    """CLI dispatch must retain the lead's validated source profile type."""
    profile = load_hypervelocity_runtime_profile(LEAD_PROFILE)

    assert isinstance(profile, SourceFollowHypervelocityProfile)
    assert profile.minimum_range_bps == pytest.approx(12.0)


@pytest.mark.integration
def test_alloc35_profile_changes_only_the_measured_risk_contract() -> None:
    """The promoted shadow candidate keeps the signal while reducing allocation."""
    candidate = load_hypervelocity_runtime_profile(ALLOC35_PROFILE)
    lead = load_hypervelocity_runtime_profile(LEAD_PROFILE)

    assert isinstance(candidate, SourceFollowHypervelocityProfile)
    assert candidate.profile_id == (
        "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"
    )
    assert candidate.margin_fraction == pytest.approx(0.35)
    assert candidate.leverage == pytest.approx(30.0)
    assert candidate.margin_fraction * candidate.leverage == pytest.approx(10.5)
    assert candidate.minimum_range_bps == lead.minimum_range_bps == 12.0
    assert candidate.target_margin_pct == lead.target_margin_pct == 8.0
    assert candidate.source_revision == lead.source_revision
    assert candidate.runtime_mode == "shadow"
    assert candidate.metalabel_mode == "observe"


@pytest.mark.integration
def test_session_alloc35_profile_changes_only_entry_hours() -> None:
    """The session candidate keeps risk and signal rules while limiting entries."""
    candidate = load_hypervelocity_runtime_profile(SESSION_ALLOC35_PROFILE)
    control = load_hypervelocity_runtime_profile(ALLOC35_PROFILE)

    assert isinstance(candidate, SourceFollowHypervelocityProfile)
    assert candidate.profile_id == (
        "hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow_v1"
    )
    assert candidate.entry_session_utc == "[06:00,15:00)"
    assert candidate.regime_policy()["session"] == "[06:00,15:00) UTC"
    assert candidate.minimum_range_bps == control.minimum_range_bps == 12.0
    assert candidate.margin_fraction == control.margin_fraction == 0.35
    assert candidate.leverage == control.leverage == 30.0
    assert candidate.target_margin_pct == control.target_margin_pct == 8.0
    assert candidate.maximum_hold_seconds == control.maximum_hold_seconds == 86_400.0
    assert candidate.metalabel_mode == "observe"


@pytest.mark.integration
def test_bidirectional_profile_routes_aligned_source_states_without_reversal() -> None:
    """The two-sided candidate names both executable sides and preserves one-way risk."""
    candidate = load_source_follow_profile(BIDIRECTIONAL_PROFILE)

    assert candidate.direction_mode == "source_follow_bidirectional"
    assert candidate.allowed_entry_states == ("TREND_UP", "TREND_DOWN", "BREAKOUT")
    assert candidate.blocked_entry_states == ("RANGE", "TRANSITION")
    assert candidate.allow_reversal_while_open is False
    assert candidate.max_positions_per_symbol == 1
    policy = candidate.regime_policy()
    assert policy["side"] == "bidirectional"
    assert policy["breakout_requires_direction"] is True
    assert policy["entry_trigger"] == (
        "confirmed_5m_aligned_trend_or_upward_breakout_primary_onset"
    )


@pytest.mark.integration
def test_runtime_dispatch_loads_bidirectional_profile() -> None:
    """CLI dispatch must not reinterpret a valid bidirectional source profile."""
    candidate = load_hypervelocity_runtime_profile(BIDIRECTIONAL_PROFILE)

    assert isinstance(candidate, SourceFollowHypervelocityProfile)
    assert candidate.direction_mode == "source_follow_bidirectional"


@pytest.mark.evidence
def test_measured_profile_preserves_signal_and_price_target_at_lower_risk() -> None:
    """Measured risk must change exposure without silently changing the signal."""
    candidate = load_hypervelocity_runtime_profile(MEASURED_PROFILE)
    control = load_source_follow_profile(BIDIRECTIONAL_PROFILE)

    assert isinstance(candidate, SourceFollowHypervelocityProfile)
    assert candidate.margin_fraction == pytest.approx(0.10)
    assert candidate.leverage == pytest.approx(5.0)
    assert candidate.margin_fraction * candidate.leverage == pytest.approx(0.50)
    assert candidate.target_margin_pct == pytest.approx(4.0 / 3.0)
    assert candidate.target_margin_pct / candidate.leverage / 100.0 == pytest.approx(
        control.target_margin_pct / control.leverage / 100.0
    )
    assert candidate.direction_mode == control.direction_mode
    assert candidate.minimum_range_bps == control.minimum_range_bps
    assert candidate.research_evidence()["evidence_status"] == (
        "development_candidate_not_live_proven"
    )
    assert candidate.research_evidence()["execution_economics_conclusive"] is False
    assert candidate.research_evidence()["active_book_gap_windows"] == 2


@pytest.mark.integration
def test_source_profile_requires_fresh_hyperliquid_warmup() -> None:
    """Pinned source continuity cannot bridge a stale cache to the live tail."""
    candidate = load_hypervelocity_runtime_profile(ALLOC35_PROFILE)
    faithful = load_hypervelocity_runtime_profile("configs/hypervelocity_faithful.toml")

    assert _requires_fresh_warmup(candidate) is True
    assert _requires_fresh_warmup(faithful) is False


@pytest.mark.integration
def test_source_follow_replay_uses_runtime_event_freshness() -> None:
    """Forward replay must not silently tighten the shadow freshness contract."""
    lead = load_source_follow_profile(LEAD_PROFILE)

    assert SourcePortfolioReplayConfig().max_event_age_ms == (
        lead.execution_max_event_age_ms
    )


def test_source_follow_profile_rejects_changed_base_profile(tmp_path: Path) -> None:
    """Inherited execution friction cannot drift without an explicit repin."""
    base = tmp_path / "base.toml"
    base.write_text("changed = true\n", encoding="utf-8")
    candidate = tmp_path / "candidate.toml"
    candidate.write_text(
        PROFILE.read_text(encoding="utf-8").replace(
            'base_profile = "hypervelocity_faithful.toml"',
            'base_profile = "base.toml"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="base profile checksum mismatch"):
        load_source_follow_profile(candidate)


@pytest.mark.integration
def test_runtime_profile_dispatch_preserves_both_profile_families() -> None:
    """CLI profile dispatch selects source-follow without changing faithful load."""
    source = load_hypervelocity_runtime_profile(PROFILE)
    faithful = load_hypervelocity_runtime_profile("configs/hypervelocity_faithful.toml")

    assert isinstance(source, SourceFollowHypervelocityProfile)
    assert not isinstance(faithful, SourceFollowHypervelocityProfile)
    assert faithful.profile_id == "hypervelocity_faithful_v2"
