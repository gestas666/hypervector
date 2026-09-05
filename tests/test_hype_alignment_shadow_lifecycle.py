"""Exact report-only lifecycle evidence for V58 HYPE alignment."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_MODULE = _ROOT / "src/hypervector/research/hype_alignment_shadow_lifecycle.py"
_CONFIG = (
    _ROOT / "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
)
_RUN = "bidirectional-observe-v58"
_PROFILE = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_DECISION = 60_000
_ENTRY = 70_000
_SOFT = _ENTRY + 28_800_000
_SOFT_CYCLE = 28_921_000


def _module() -> ModuleType:
    assert _MODULE.is_file(), "HYPE alignment shadow lifecycle module is missing"
    spec = spec_from_file_location("hype_alignment_shadow_lifecycle", _MODULE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_soft_hold_exits_when_fresh_structure_is_not_supported() -> None:
    """The first fresh unsupported soft decision must consume exact depth."""
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    records = _records(config.profile_fingerprint, soft_states="RANGE")

    report = module.build_hype_alignment_shadow_resolution(
        records,
        config=config,
        run_id=_RUN,
        prospective_start_ms=0,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "maximum_hold_seconds"
    assert execution["exit_time_ms"] == _SOFT_CYCLE + 1_000
    assert execution["policy_exit_evidence"]["structure_alignment_score"] == 0.0
    assert report["contract"]["soft_maximum_hold_minutes"] == 480
    assert report["contract"]["maximum_hold_minutes"] == 1_440
    assert report["contract"]["maximum_hold_evidence_maximum_age_seconds"] == 60
    assert report["contract"]["execution_authority"] == "none"
    rejected = report["rejected_onset_diagnostic"]
    assert rejected["fresh_onsets"] == 1
    assert rejected["eligible_fresh_onsets"] == 1
    assert rejected["rejected_fresh_onsets"] == 0
    assert rejected["strategy_change_supported"] is False


def test_supported_soft_hold_extends_until_structure_is_lost() -> None:
    """Fresh support may extend, but later loss must close before the hard cap."""
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    records = _records(config.profile_fingerprint, soft_states="TREND_UP")
    records.extend(_context_cycle(_SOFT_CYCLE + 60_000, "RANGE"))
    records.append(_books(_SOFT_CYCLE + 61_000, bid=100.2, ask=100.3))

    report = module.build_hype_alignment_shadow_resolution(
        records,
        config=config,
        run_id=_RUN,
        prospective_start_ms=0,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    execution = report["latest_executions"][0]
    evidence = execution["policy_exit_evidence"]
    assert execution["exit_reason"] == "maximum_hold_seconds"
    assert execution["exit_time_ms"] == _SOFT_CYCLE + 61_000
    assert evidence["soft_decision"]["outcome"] == "extend"
    assert evidence["structure_alignment_score"] == 0.0


def test_stale_soft_hold_evidence_fails_closed() -> None:
    """A stale context cannot silently extend an open virtual lifecycle."""
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    records = _records(
        config.profile_fingerprint,
        soft_states="TREND_UP",
        context_decision_ms=_SOFT_CYCLE - 121_000,
    )

    report = module.build_hype_alignment_shadow_resolution(
        records,
        config=config,
        run_id=_RUN,
        prospective_start_ms=0,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "maximum_hold_evidence_stale"
    assert execution["policy_exit_evidence"]["provider_evidence_age_ms"] > 60_000


def test_v58_hype_execution_drift_is_rejected() -> None:
    """The observer cannot alias a cheaper stop under the frozen provider ID."""
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    providers = tuple(
        replace(
            provider,
            execution=replace(provider.execution, stop_bps=60.0),
        )
        if provider.strategy_id
        == "hype_breakout_compression_alignment_bidirectional_v2"
        else provider
        for provider in config.providers
    )

    with pytest.raises(ValueError, match="HYPE alignment execution contract"):
        module.build_hype_alignment_shadow_resolution(
            _records(config.profile_fingerprint, soft_states="RANGE"),
            config=replace(config, providers=providers),
            run_id=_RUN,
            prospective_start_ms=0,
            funding_evidence=None,
            taker_fee_rate=0.00045,
        )


def test_pre_preregistration_entry_is_excluded() -> None:
    """Observed history before the frozen boundary cannot become evidence."""
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    report = module.build_hype_alignment_shadow_resolution(
        _records(config.profile_fingerprint, soft_states="RANGE"),
        config=config,
        run_id=_RUN,
        prospective_start_ms=_DECISION + 1,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    assert report["summary"]["resolved"] == 0
    assert report["latest_attempts"] == []


def _records(
    fingerprint: str,
    *,
    soft_states: str,
    context_decision_ms: int | None = None,
) -> list[dict[str, object]]:
    records = [
        _row("configuration_identity", _identity(fingerprint), 0),
        _row("intent_routing", _routing(_DECISION, "TREND_UP", True), 61_000),
        _books(_ENTRY, bid=99.9, ask=100.0),
    ]
    records.extend(
        _books(time_ms, bid=99.9, ask=100.0)
        for time_ms in range(_ENTRY + 60_000, _SOFT_CYCLE, 60_000)
    )
    records.extend(
        _context_cycle(
            _SOFT_CYCLE,
            soft_states,
            decision_ms=context_decision_ms,
        )
    )
    records.append(_books(_SOFT_CYCLE + 1_000, bid=99.8, ask=99.9))
    return records


def _context_cycle(
    observed_ms: int, state: str, *, decision_ms: int | None = None
) -> list[dict[str, object]]:
    decision = observed_ms - 1_000 if decision_ms is None else decision_ms
    canonical = _evaluation("canonical_regime_telemetry_v1", decision, state, False)
    provider = _routing(decision, state, False)
    return [
        _row(
            "canonical_regime_evaluations",
            {"contract": {"execution_authority": "none"}, "evaluations": [canonical]},
            observed_ms,
        ),
        _row("intent_routing", provider, observed_ms),
    ]


def _identity(fingerprint: str) -> dict[str, object]:
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "profile_fingerprint": fingerprint,
        "enabled_symbols": ["HYPE"],
    }


def _routing(decision_ms: int, state: str, eligible: bool) -> dict[str, object]:
    return {
        "evaluations": [
            _evaluation(
                "hype_breakout_compression_alignment_bidirectional_v2",
                decision_ms,
                state,
                eligible,
            )
        ],
        "actions": [],
        "withheld": [],
    }


def _evaluation(
    strategy_id: str, decision_ms: int, state: str, eligible: bool
) -> dict[str, object]:
    side = "long"
    return {
        "strategy_id": strategy_id,
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": 100.0,
        "decision_action": "enter_long" if eligible else "hold",
        "eligible": eligible,
        "reason": "ready" if eligible else "no_trigger",
        "side": side if strategy_id != "canonical_regime_telemetry_v1" else None,
        "primary_regime": state,
        "state_1m": state,
        "state_5m": state,
        "context_15m": state,
        "confidence": 0.8,
        "readiness": {
            "side": side,
            "blockers": [] if eligible else ["no_trigger"],
            "metrics": {
                "structural_direction": side,
                "canonical_breakout_onset_fresh": eligible,
                "breakout_side": side if eligible else None,
                "breakout_side_relation": "aligned" if eligible else "unavailable",
            },
        },
    }


def _books(time_ms: int, *, bid: float, ask: float) -> dict[str, object]:
    return _row(
        "market_books",
        {
            "books": {
                "HYPE": {
                    "symbol": "HYPE",
                    "source": "hyperliquid_mainnet_l2_rest",
                    "exchange_ts_ms": time_ms - 10,
                    "recv_ts_ms": time_ms,
                    "bids": [{"price": bid, "size": 100.0, "orders": 1}],
                    "asks": [{"price": ask, "size": 100.0, "orders": 1}],
                }
            }
        },
        time_ms,
    )


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": _PROFILE,
        "run_fingerprint": "fixture-run",
        "run_id": _RUN,
        "payload": payload,
    }
