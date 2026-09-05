"""Exact identities, paths and parsed source facts for pressure journals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hypervector.live.hip3_breakout_shadow_specs import (
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
    SNDK_SHADOW_SPEC,
)
from hypervector.live.hip3_fresh15_condition_telemetry import (
    Hip3Fresh15ConditionTelemetry,
)

INDEX_SYMBOLS = (SP500_SHADOW_SPEC.symbol, SPCX_SHADOW_SPEC.symbol)
HIP3_INDEX_FRESH15_V3_STRATEGY = SP500_SHADOW_SPEC.provider_id
HIP3_SNDK_FRESH15_V4_STRATEGY = SNDK_SHADOW_SPEC.provider_id
JOURNAL_SPECS = {
    SP500_SHADOW_SPEC.symbol: SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC.symbol: SPCX_SHADOW_SPEC,
    SNDK_SHADOW_SPEC.symbol: SNDK_SHADOW_SPEC,
}
DEFAULT_JOURNALS = {
    "xyz:SNDK": Path("data/live/research/xyz_sndk_fresh15_v4_decisions.jsonl"),
    "xyz:SP500": Path("data/live/research/xyz_sp500_fresh15_v3_decisions.jsonl"),
    "xyz:SPCX": Path("data/live/research/xyz_spcx_fresh15_v3_decisions.jsonl"),
}
DEFAULT_OBSERVER_STATES = {
    "xyz:SNDK": (
        Path("data/runtime/research/xyz_sndk_fresh15_v4_latest.json"),
        Path("data/runtime/research/xyz_sndk_fresh15_v4_cursor.json"),
    ),
    "xyz:SP500": (
        Path("data/runtime/research/xyz_sp500_fresh15_v3_latest.json"),
        Path("data/runtime/research/xyz_sp500_fresh15_v3_cursor.json"),
    ),
    "xyz:SPCX": (
        Path("data/runtime/research/xyz_spcx_fresh15_v3_latest.json"),
        Path("data/runtime/research/xyz_spcx_fresh15_v3_cursor.json"),
    ),
}


CONFIRMATION_REASONS = {
    spec.provider_id: f"fresh15_{spec.provider_id.rsplit('_', 1)[1]}_breakout_pressure_confirmed"
    for spec in JOURNAL_SPECS.values()
}


@dataclass(frozen=True)
class Hip3Fresh15Decision:
    """Validated source facts shared by prospective pressure journal adapters."""

    provider_id: str
    profile_id: str
    symbol: str
    decision_time_ms: int
    side: str | None
    eligible: bool
    imbalance: float
    pressure_fresh: bool
    pressure_status: str
    pressure_source: str
    pressure_scan_complete: bool
    pressure_exchange_ts_ms: int | None
    pressure_recv_ts_ms: int | None
    snapshot_count: int
    boundary_age_ms: int | None
    observed_at_ms: int
    decision_delay_ms: int
    prospective: bool
    history_complete: bool
    condition_anatomy: Hip3Fresh15ConditionTelemetry | None
