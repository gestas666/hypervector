"""Recovery-batch persistence for telemetry-only canonical regimes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_ledger import SolLiveLedger

_OBSERVED = datetime(2026, 8, 11, 4, 3, tzinfo=UTC)


def test_accepts_ordered_multi_bar_recovery_for_one_symbol(tmp_path: Path) -> None:
    """Two recovered BTC closes retain distinct decision identities."""
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_canonical_regimes((_evaluation(1_000), _evaluation(2_000)))

    row = ledger.read_all()[0]
    assert row["event_type"] == "canonical_regime_evaluations"
    assert [value["decision_time_ms"] for value in row["payload"]["evaluations"]] == [
        1_000,
        2_000,
    ]


def test_rejects_duplicate_recovery_identity(tmp_path: Path) -> None:
    """One symbol and close cannot be persisted twice in the same batch."""
    telemetry, _ = _telemetry(tmp_path)
    evaluation = _evaluation(1_000)

    with pytest.raises(ValueError, match="duplicate canonical regime evaluation"):
        telemetry.emit_canonical_regimes((evaluation, evaluation))


def test_rejects_unordered_recovery_batch(tmp_path: Path) -> None:
    """Recovery evidence must retain completed-decision chronology."""
    telemetry, _ = _telemetry(tmp_path)

    with pytest.raises(ValueError, match="canonical regime evaluations are unordered"):
        telemetry.emit_canonical_regimes((_evaluation(2_000), _evaluation(1_000)))


def _telemetry(tmp_path: Path) -> tuple[MultiAssetCohortTelemetry, SolLiveLedger]:
    config = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml",
        mode="observe",
    )
    ledger = SolLiveLedger(
        path=tmp_path / "observe" / "canonical" / "decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="canonical-recovery-test",
        execution_mode="observe",
    )
    return (
        MultiAssetCohortTelemetry(
            config=config, ledger=ledger, now_fn=lambda: _OBSERVED
        ),
        ledger,
    )


def _evaluation(decision_time_ms: int) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=CANONICAL_REGIME_TELEMETRY_STRATEGY,
        symbol="BTC",
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="regime_observation",
        eligible=False,
        reason="canonical_regime_observation",
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=0,
            conditions_required=1,
            blockers=("awaiting_hourly_sma_cross",),
            indicators=("5m RANGE",),
            metrics={"structural_direction": "neutral"},
        ),
        primary_regime="RANGE",
        state_1m="RANGE",
        state_5m="RANGE",
        context_15m="RANGE",
        confidence=0.5,
        backend_non_action_reason="telemetry_only_no_execution_authority",
    )
