"""Checksum-pinned shadow profile for the measured source-follow candidate."""

from __future__ import annotations

import hashlib
import math
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping, cast

from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    PINNED_SOURCE_HASHES,
    verify_source_files,
)
from hypervector.strategies.hypervelocity_profile import (
    HypervelocityProfile,
    load_hypervelocity_profile,
)

_CONTROL_PROFILE_ID = "hypervelocity_source_follow_shadow_v1"
_LEAD_PROFILE_ID = "hypervelocity_source_follow_minrange12_shadow_v1"
_ALLOC35_PROFILE_ID = "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"
_SESSION_ALLOC35_PROFILE_ID = (
    "hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow_v1"
)
_BIDIRECTIONAL_ALLOC35_PROFILE_ID = (
    "hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow_v1"
)
_MEASURED_BIDIRECTIONAL_PROFILE_ID = (
    "hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow_v1"
)
_SOURCE_TARGET_PRICE_FRACTION = 8.0 / 30.0 / 100.0
_MEASURED_TARGET_MARGIN_PCT = _SOURCE_TARGET_PRICE_FRACTION * 5.0 * 100.0


@dataclass(frozen=True)
class _SourceProfileContract:
    minimum_range_bps: float
    margin_fraction: float
    leverage: float
    notional_fraction: float
    target_margin_pct: float
    entry_session_utc: str
    direction_mode: str
    primary_regime: str
    side: str


_PROFILE_CONTRACTS = {
    _CONTROL_PROFILE_ID: _SourceProfileContract(
        0.0, 0.50, 30.0, 15.0, 8.0, "24/7", "source_follow_short", "TREND_DOWN", "short"
    ),
    _LEAD_PROFILE_ID: _SourceProfileContract(
        12.0,
        0.50,
        30.0,
        15.0,
        8.0,
        "24/7",
        "source_follow_short",
        "TREND_DOWN",
        "short",
    ),
    _ALLOC35_PROFILE_ID: _SourceProfileContract(
        12.0,
        0.35,
        30.0,
        10.5,
        8.0,
        "24/7",
        "source_follow_short",
        "TREND_DOWN",
        "short",
    ),
    _SESSION_ALLOC35_PROFILE_ID: _SourceProfileContract(
        12.0,
        0.35,
        30.0,
        10.5,
        8.0,
        "[06:00,15:00)",
        "source_follow_short",
        "TREND_DOWN",
        "short",
    ),
    _BIDIRECTIONAL_ALLOC35_PROFILE_ID: _SourceProfileContract(
        12.0,
        0.35,
        30.0,
        10.5,
        8.0,
        "24/7",
        "source_follow_bidirectional",
        "TREND_UP_OR_TREND_DOWN_OR_UPWARD_BREAKOUT",
        "bidirectional",
    ),
    _MEASURED_BIDIRECTIONAL_PROFILE_ID: _SourceProfileContract(
        12.0,
        0.10,
        5.0,
        0.50,
        _MEASURED_TARGET_MARGIN_PCT,
        "24/7",
        "source_follow_bidirectional",
        "TREND_UP_OR_TREND_DOWN_OR_UPWARD_BREAKOUT",
        "bidirectional",
    ),
}


@dataclass(frozen=True)
class SourceFollowHypervelocityProfile(HypervelocityProfile):
    """Operational profile plus the exact causal source signal contract."""

    base_profile_sha256: str
    source_revision: str
    source_backend_root: Path
    minimum_confidence: float
    minimum_range_bps: float
    maximum_range_bps: float
    decision_delay_seconds: float
    entry_pulse_seconds: float
    maximum_hold_seconds: float
    entry_session_utc: str
    research_status: str = "not_reported"
    research_artifact: Path | None = None
    research_artifact_sha256: str | None = None
    execution_economics_conclusive: bool | None = None
    active_book_gap_windows: int | None = None

    def research_evidence(self) -> dict[str, object]:
        """Return report-only development evidence without execution authority."""
        return {
            "evidence_status": self.research_status,
            "evidence_artifact": (
                str(self.research_artifact)
                if self.research_artifact is not None
                else None
            ),
            "evidence_artifact_sha256": self.research_artifact_sha256,
            "execution_economics_conclusive": self.execution_economics_conclusive,
            "active_book_gap_windows": self.active_book_gap_windows,
        }

    def regime_policy(self) -> dict[str, object]:
        """Return backend telemetry for the source regime actually in authority."""
        bidirectional = self.direction_mode == "source_follow_bidirectional"
        return {
            "engine": "pinned_hypertrader_source_follow_v1",
            "source_revision": self.source_revision,
            "execution_timeframe": "5m",
            "primary_timeframe": "5m",
            "context_timeframe": "15m",
            "classified_timeframes": ["5m"],
            "state_1m_role": "not_classified",
            "context_role": "not_classified",
            "context_is_hard_gate": False,
            "entry_trigger": (
                "confirmed_5m_aligned_trend_or_upward_breakout_primary_onset"
                if bidirectional
                else "confirmed_5m_trend_down_primary_onset"
            ),
            "side": "bidirectional" if bidirectional else "short",
            "onset_only": True,
            "decision_delay_seconds": self.decision_delay_seconds,
            "entry_pulse_seconds": self.entry_pulse_seconds,
            "minimum_confidence": self.minimum_confidence,
            "minimum_completed_5m_range_bps": self.minimum_range_bps,
            "maximum_completed_5m_range_bps": self.maximum_range_bps,
            "session": (
                self.entry_session_utc
                if self.entry_session_utc == "24/7"
                else f"{self.entry_session_utc} UTC"
            ),
            "maximum_hold_seconds": self.maximum_hold_seconds,
            "allowed_entry_states": list(self.allowed_entry_states),
            "blocked_entry_states": list(self.blocked_entry_states),
            "breakout_requires_direction": self.breakout_requires_direction,
            "confidence_is_gate": self.confidence_is_gate,
        }


def load_source_follow_profile(path: Path | str) -> SourceFollowHypervelocityProfile:
    """Load and fail-closed validate the source-follow shadow candidate."""
    profile_path = Path(path)
    raw = _load_toml(profile_path)
    profile_id = _validate_identity(raw)
    contract = _PROFILE_CONTRACTS[profile_id]
    base_path = _relative_path(profile_path, _text(raw, "base_profile"))
    base_sha = _text(raw, "base_profile_sha256")
    _verify_sha256(base_path, base_sha)
    base = load_hypervelocity_profile(base_path)
    signal = _section(raw, "signal")
    allocation = _section(raw, "allocation")
    exits = _section(raw, "exit")
    execution = _section(raw, "execution")
    model = _section(raw, "model")
    runtime = _section(raw, "runtime")
    _validate_candidate(
        signal,
        allocation,
        exits,
        execution,
        model,
        runtime,
        contract=contract,
    )
    evidence = _research_evidence(profile_path, raw, profile_id)
    backend = _relative_path(profile_path, _text(signal, "upstream_backend"))
    revision = _text(signal, "source_revision")
    verify_source_files(
        backend,
        expected_hashes=PINNED_SOURCE_HASHES,
        revision=revision,
    )
    return _profile_from_sections(
        base,
        profile_id=profile_id,
        base_sha=base_sha,
        backend=backend,
        signal=signal,
        allocation=allocation,
        exits=exits,
        runtime=runtime,
        contract=contract,
        evidence=evidence,
    )


def _profile_from_sections(
    base: HypervelocityProfile,
    *,
    profile_id: str,
    base_sha: str,
    backend: Path,
    signal: Mapping[str, object],
    allocation: Mapping[str, object],
    exits: Mapping[str, object],
    runtime: Mapping[str, object],
    contract: _SourceProfileContract,
    evidence: Mapping[str, object],
) -> SourceFollowHypervelocityProfile:
    allowed_states, blocked_states = _entry_states(contract.direction_mode)
    values = {field.name: getattr(base, field.name) for field in fields(base)}
    values.update(
        profile_id=profile_id,
        direction_mode=contract.direction_mode,
        margin_fraction=_number(allocation, "margin_fraction"),
        leverage=_number(allocation, "leverage"),
        target_margin_pct=_number(exits, "target_margin_pct"),
        open_position_range_policy="hold_until_target_or_maximum_hold",
        entry_ttl_seconds=60.0,
        expired_entry_rearm_policy="source_event_reset",
        same_direction_reentry_policy="source_event_reset",
        reentry_cooldown_bars=0,
        initial_cash_usd=_number(runtime, "initial_cash_usd"),
        lookback_days=_integer(runtime, "lookback_days"),
        allowed_entry_states=allowed_states,
        blocked_entry_states=blocked_states,
        confidence_is_gate=True,
    )
    return SourceFollowHypervelocityProfile(
        **values,
        base_profile_sha256=base_sha,
        source_revision=_text(signal, "source_revision"),
        source_backend_root=backend,
        minimum_confidence=_number(signal, "minimum_confidence"),
        minimum_range_bps=_number(signal, "minimum_completed_5m_range_bps"),
        maximum_range_bps=_number(signal, "maximum_completed_5m_range_bps"),
        decision_delay_seconds=_number(signal, "decision_delay_seconds"),
        entry_pulse_seconds=_number(signal, "entry_pulse_seconds"),
        maximum_hold_seconds=_number(exits, "maximum_hold_seconds"),
        entry_session_utc=_text(signal, "session"),
        research_status=_text(evidence, "evidence_status"),
        research_artifact=cast(Path | None, evidence.get("evidence_artifact")),
        research_artifact_sha256=cast(
            str | None, evidence.get("evidence_artifact_sha256")
        ),
        execution_economics_conclusive=cast(
            bool | None, evidence.get("execution_economics_conclusive")
        ),
        active_book_gap_windows=cast(
            int | None, evidence.get("active_book_gap_windows")
        ),
    )


def _entry_states(direction_mode: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if direction_mode == "source_follow_bidirectional":
        return ("TREND_UP", "TREND_DOWN", "BREAKOUT"), ("RANGE", "TRANSITION")
    return ("TREND_DOWN",), ("RANGE", "TRANSITION", "TREND_UP", "BREAKOUT")


def _validate_identity(raw: Mapping[str, object]) -> str:
    profile_id = _text(raw, "profile")
    if profile_id not in _PROFILE_CONTRACTS:
        raise ValueError(f"unsupported source-follow profile: {profile_id!r}")
    contract = _PROFILE_CONTRACTS[profile_id]
    expected = {
        "symbol": "BTC",
        "timeframe": "1m",
        "strategy_id": "hypervelocity_1m_scalper",
        "position_mode": "one_way",
        "max_positions_per_symbol": 1,
        "direction_mode": contract.direction_mode,
        "allow_reversal_while_open": False,
        "switch_after_exit": True,
    }
    for key, value in expected.items():
        _expect(raw, key, value)
    return profile_id


def _validate_candidate(
    signal: Mapping[str, object],
    allocation: Mapping[str, object],
    exits: Mapping[str, object],
    execution: Mapping[str, object],
    model: Mapping[str, object],
    runtime: Mapping[str, object],
    *,
    contract: _SourceProfileContract,
) -> None:
    _validate_signal(signal, contract)
    _expect(allocation, "margin_fraction", contract.margin_fraction)
    _expect(allocation, "leverage", contract.leverage)
    _expect(allocation, "notional_fraction", contract.notional_fraction)
    _expect(allocation, "margin_mode", "isolated")
    _validate_exit(exits, contract)
    _validate_execution(execution)
    _expect(model, "mode", "observe")
    _expect(model, "may_filter", False)
    _expect(model, "may_scale", False)
    _expect(runtime, "mode", "shadow")
    _expect(runtime, "initial_cash_usd", 15_000.0)
    _expect(runtime, "lookback_days", 30)
    _expect(runtime, "strict_hl_only", True)
    _expect(runtime, "metalabel_mode", "observe")


def _validate_signal(
    signal: Mapping[str, object],
    contract: _SourceProfileContract,
) -> None:
    expected = {
        "source_revision": PINNED_HYPERTRADER_REVISION,
        "primary_timeframe": "5m",
        "primary_regime": contract.primary_regime,
        "side": contract.side,
        "onset_only": True,
        "minimum_confidence": 0.70,
        "minimum_completed_5m_range_bps": contract.minimum_range_bps,
        "maximum_completed_5m_range_bps": 100.0,
        "decision_delay_seconds": 300.0,
        "entry_pulse_seconds": 60.0,
        "session": contract.entry_session_utc,
    }
    for key, value in expected.items():
        _expect(signal, key, value)


def _validate_exit(
    exits: Mapping[str, object], contract: _SourceProfileContract
) -> None:
    _expect(exits, "target_margin_pct", contract.target_margin_pct)
    _expect(exits, "target_price_fraction", _SOURCE_TARGET_PRICE_FRACTION)
    _expect(exits, "maximum_hold_seconds", 86_400.0)
    _expect(exits, "fixed_stop", "none")
    _expect(exits, "open_position_range_policy", "hold_until_target_or_maximum_hold")


def _validate_execution(execution: Mapping[str, object]) -> None:
    expected = {
        "entry_order_type": "limit",
        "entry_time_in_force": "post_only",
        "entry_ttl_seconds": 60.0,
        "expired_entry_rearm_policy": "source_event_reset",
        "same_direction_reentry_policy": "source_event_reset",
        "reentry_cooldown_bars": 0,
        "fill_rule": "public_l2_trade_event_tape",
        "maximum_hold_exit": "first_fresh_bbo_taker",
        "paper_submit_enabled": False,
        "live_enabled": False,
        "execution_authority": "shadow_only",
    }
    for key, value in expected.items():
        _expect(execution, key, value)


def _research_evidence(
    profile_path: Path,
    raw: Mapping[str, object],
    profile_id: str,
) -> dict[str, object]:
    if profile_id != _MEASURED_BIDIRECTIONAL_PROFILE_ID:
        return {
            "evidence_status": "not_reported",
            "evidence_artifact": None,
            "evidence_artifact_sha256": None,
            "execution_economics_conclusive": None,
            "active_book_gap_windows": None,
        }
    section = _section(raw, "evidence")
    _expect(section, "status", "development_candidate_not_live_proven")
    _expect(section, "execution_economics_conclusive", False)
    _expect(section, "active_book_gap_windows", 2)
    artifact = _relative_path(profile_path, _text(section, "artifact"))
    expected_sha = _text(section, "artifact_sha256")
    _verify_sha256(artifact, expected_sha)
    return {
        "evidence_status": _text(section, "status"),
        "evidence_artifact": artifact,
        "evidence_artifact_sha256": expected_sha,
        "execution_economics_conclusive": False,
        "active_book_gap_windows": 2,
    }


def _load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"source-follow config not found: {path}")
    with path.open("rb") as handle:
        return cast(dict[str, object], tomllib.load(handle))


def _relative_path(config: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (config.parent / path).resolve()


def _verify_sha256(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"source-follow base profile not found: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"base profile checksum mismatch expected={expected} actual={actual}"
        )


def _section(raw: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"source-follow config requires [{name}]")
    return cast(dict[str, object], value)


def _expect(section: Mapping[str, object], key: str, expected: object) -> None:
    actual = section.get(key)
    if actual != expected:
        raise ValueError(f"{key} must be {expected!r}, got {actual!r}")


def _text(section: Mapping[str, object], key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _number(section: Mapping[str, object], key: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _integer(section: Mapping[str, object], key: str) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value
