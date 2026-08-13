"""Fail-closed v39 acceptance for independent canonical regime evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from hypervector.research.v39_poststart_acceptance import (
    build_v39_poststart_acceptance,
)
from test_v39_poststart_acceptance import _NOW, _checkpoint, _config


def test_rejects_missing_canonical_regime_telemetry() -> None:
    """Route coverage cannot substitute for the retired Range telemetry source."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"].pop("canonical_regime_telemetry", None)

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert "canonical_regime_telemetry_missing" in report["reasons"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("future", "canonical_regime_future_evidence:BTC"),
        ("stale", "canonical_regime_stale:BTC"),
        ("incomplete", "canonical_regime_fields_incomplete:BTC"),
        ("executable", "canonical_regime_contract_invalid"),
    ],
)
def test_rejects_noncausal_incomplete_or_executable_canonical_evidence(
    mutation: str,
    reason: str,
) -> None:
    """Canonical acceptance requires fresh complete telemetry-only rows."""
    config = _config()
    checkpoint = _checkpoint(config)
    canonical = deepcopy(checkpoint["audit"]["canonical_regime_telemetry"])
    checkpoint["audit"]["canonical_regime_telemetry"] = canonical
    btc = canonical["by_symbol"]["BTC"]
    if mutation == "future":
        btc["latest"]["decision_time_ms"] += 10_000
    elif mutation == "stale":
        btc["latest_observed_at_utc"] = "2026-08-11T03:55:00+00:00"
        btc["latest"]["decision_time_ms"] = 1_786_420_500_000
    elif mutation == "incomplete":
        btc["latest"]["state_5m"] = None
    else:
        canonical["contract"]["execution_authority"] = "hyperliquid_mainnet"

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert reason in report["reasons"]


def test_rejects_unknown_canonical_state_as_unavailable() -> None:
    """Warmup UNKNOWN remains neutral telemetry, not acceptance evidence."""
    config = _config()
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["canonical_regime_telemetry"]["by_symbol"]["BTC"]["latest"][
        "state_1m"
    ] = "UNKNOWN"

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert "canonical_regime_unavailable:BTC" in report["reasons"]


def test_rejects_fresh_receipt_of_stale_canonical_decision() -> None:
    """A fresh persistence timestamp cannot refresh old market evidence."""
    config = _config()
    checkpoint = _checkpoint(config)
    canonical = checkpoint["audit"]["canonical_regime_telemetry"]
    btc = canonical["by_symbol"]["BTC"]
    btc["latest_observed_at_utc"] = (_NOW - timedelta(seconds=5)).isoformat()
    btc["latest"]["decision_time_ms"] = int(
        (_NOW - timedelta(minutes=5)).timestamp() * 1_000
    )

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is False
    assert "canonical_regime_stale:BTC" in report["reasons"]


def test_accepts_three_timeframe_bias_sum_at_its_declared_bounds() -> None:
    """MTF bias is a three-vote sum, not a single direction code."""
    config = _config()
    checkpoint = _checkpoint(config)
    metrics = checkpoint["audit"]["canonical_regime_telemetry"]["by_symbol"]["BTC"][
        "latest"
    ]["readiness"]["metrics"]
    metrics["mtf_5m_bias"] = -3
    metrics["mtf_15m_bias"] = 3

    report = build_v39_poststart_acceptance(checkpoint, config, now_utc=_NOW)

    assert report["accepted"] is True
