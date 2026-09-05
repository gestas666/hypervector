"""Live-parity tests for the HYPE compression-breakout provider."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pandas as pd
import pytest

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hype_breakout_compression_provider import (
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
    HypeCompressionBreakoutCollector,
)
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
    HypeCompressionAlignmentCollector,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.multi_asset_default_collectors import _native_collector
from hypervector.live.provider_readiness import SignalReadiness

_DECISION_MS = int(pd.Timestamp("2026-08-10T20:00:00Z").timestamp() * 1_000)
_CANONICAL = "hype_breakout_onset_bidirectional_v1"


def _source(
    *,
    side: str = "long",
    bbwp_5m: float | None = 45.0,
    prior_bbwp: float | None = 35.0,
    body_bps: float | None = -2.0,
    relation: str = "aligned",
) -> ProviderEvaluation:
    metrics: dict[str, object] = {
        "entry_feature_status": "measured",
        "authoritative_5m_bbwp_percentile": bbwp_5m,
        "prior_bbwp_min_15m": prior_bbwp,
        "directional_bar_body_bps": body_bps,
        "breakout_side_relation": relation,
    }
    return ProviderEvaluation(
        strategy_id=_CANONICAL,
        symbol="HYPE",
        decision_time_ms=_DECISION_MS,
        reference_price=55.0,
        decision_action=f"enter_{side}",
        eligible=True,
        reason="breakout_onset_directional",
        side=side,
        readiness=SignalReadiness(
            side=side,
            conditions_met=3,
            conditions_required=3,
            blockers=(),
            indicators=("CANONICAL",),
            metrics=metrics,
        ),
        trigger="5m_breakout_onset",
        primary_regime="BREAKOUT",
        state_1m="TREND_UP" if side == "long" else "TREND_DOWN",
        state_5m="BREAKOUT",
        context_15m="RANGE",
        confidence=0.7,
    )


def _canonical(
    source: ProviderEvaluation, *, fresh: bool = True
) -> Callable[..., IntentBatch]:
    intents = (
        (
            StrategyIntent(
                strategy_id=_CANONICAL,
                symbol="HYPE",
                side=source.side or "long",
                decision_time_ms=source.decision_time_ms,
                reference_price=source.reference_price,
                reason="test",
            ),
        )
        if fresh
        else ()
    )

    def collect(*args: object, **kwargs: object) -> IntentBatch:
        del args, kwargs
        return IntentBatch(intents, _DECISION_MS, (source,))

    return collect


@pytest.mark.parametrize("side", ["long", "short"])
def test_hype_filter_preserves_both_sides_and_exact_thresholds(side: str) -> None:
    """A fresh canonical onset passes only the frozen development contract."""
    collector = HypeCompressionBreakoutCollector(
        canonical_collector=_canonical(_source(side=side)),
        execution_enabled=True,
    )

    batch = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-10T20:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )

    assert [(intent.strategy_id, intent.side) for intent in batch.intents] == [
        (HYPE_COMPRESSION_BREAKOUT_STRATEGY, side)
    ]
    readiness = batch.evaluations[0].readiness
    assert readiness.conditions_required == 4
    assert readiness.metrics["maximum_5m_bbwp_percentile"] == 50.0
    assert readiness.metrics["maximum_prior_bbwp_min_15m"] == 40.0
    assert readiness.metrics["candidate_authority"] == "automatic_execution"


@pytest.mark.parametrize(
    ("bbwp_5m", "prior_bbwp", "body_bps", "blocker"),
    [
        (50.1, 35.0, -2.0, "authoritative_5m_compression_absent"),
        (45.0, 40.1, -2.0, "prior_compression_absent"),
        (45.0, 35.0, 0.1, "directional_pullback_absent"),
    ],
)
def test_hype_filter_requires_every_frozen_feature(
    bbwp_5m: float,
    prior_bbwp: float,
    body_bps: float,
    blocker: str,
) -> None:
    """Every mechanistic feature is conjunctive and visible when blocked."""
    collector = HypeCompressionBreakoutCollector(
        canonical_collector=_canonical(
            _source(bbwp_5m=bbwp_5m, prior_bbwp=prior_bbwp, body_bps=body_bps)
        )
    )

    batch = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-10T20:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )

    assert batch.intents == ()
    assert blocker in batch.evaluations[0].readiness.blockers


def test_hype_filter_fails_closed_on_missing_features_or_stale_source() -> None:
    """Unmeasured features and startup seed evaluations cannot route."""
    missing = HypeCompressionBreakoutCollector(
        canonical_collector=_canonical(_source(bbwp_5m=None))
    )
    stale = HypeCompressionBreakoutCollector(
        canonical_collector=_canonical(_source(), fresh=False)
    )
    arguments = {
        "symbol": "HYPE",
        "observed_at": pd.Timestamp("2026-08-10T20:00:30Z"),
        "after_decision_time_ms": _DECISION_MS - 60_000,
    }

    missing_batch = missing(pd.DataFrame(), **arguments)
    stale_batch = stale(pd.DataFrame(), **arguments)

    assert missing_batch.evaluations[0].reason == "entry_features_unavailable"
    assert stale_batch.evaluations[0].reason == "canonical_intent_not_fresh"
    assert not missing_batch.intents and not stale_batch.intents


def test_hype_filter_rejects_other_symbols() -> None:
    """The frozen identity cannot silently transfer to another market."""
    collector = HypeCompressionBreakoutCollector(
        canonical_collector=_canonical(_source())
    )

    with pytest.raises(ValueError, match="supports HYPE only"):
        collector(
            pd.DataFrame(),
            symbol="SOL",
            observed_at=pd.Timestamp("2026-08-10T20:00:30Z"),
            after_decision_time_ms=_DECISION_MS - 60_000,
        )


@pytest.mark.parametrize("side", ["long", "short"])
def test_alignment_revision_routes_both_aligned_sides(side: str) -> None:
    """The versioned repair retains only agreement under a new identity."""
    collector = HypeCompressionAlignmentCollector(
        canonical_collector=_canonical(_source(side=side, relation="aligned")),
        execution_enabled=True,
    )

    batch = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-10T20:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )

    assert [(intent.strategy_id, intent.side) for intent in batch.intents] == [
        (HYPE_COMPRESSION_ALIGNMENT_STRATEGY, side)
    ]
    assert batch.evaluations[0].readiness.metrics["alignment_only"] is True
    assert batch.evaluations[0].readiness.conditions_required == 5


@pytest.mark.parametrize(
    ("relation", "reason"),
    [
        ("opposed", "breakout_side_opposed"),
        ("unavailable", "breakout_side_unavailable"),
    ],
)
def test_alignment_revision_fails_closed_without_agreement(
    relation: str,
    reason: str,
) -> None:
    """Opposed or absent side evidence cannot leak a base compression intent."""
    collector = HypeCompressionAlignmentCollector(
        canonical_collector=_canonical(_source(relation=relation)),
        execution_enabled=True,
    )

    batch = collector(
        pd.DataFrame(),
        symbol="HYPE",
        observed_at=pd.Timestamp("2026-08-10T20:00:30Z"),
        after_decision_time_ms=_DECISION_MS - 60_000,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].reason == reason
    assert reason in batch.evaluations[0].readiness.blockers


def test_alignment_revision_has_a_default_runtime_collector() -> None:
    """A successor config cannot validate yet fail during collector assembly."""
    provider = SimpleNamespace(
        strategy_id=HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
        execution_symbols=("HYPE",),
        executable_sides=lambda _symbol: frozenset({"long", "short"}),
    )
    config = SimpleNamespace(mode="live")

    collector = _native_collector(provider, config)

    assert isinstance(collector, HypeCompressionAlignmentCollector)
