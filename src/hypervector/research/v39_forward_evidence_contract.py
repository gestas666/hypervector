"""Frozen identity and freshness contract for v39 forward evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

Record = Mapping[str, object]

PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39"
)
PROFILE_FINGERPRINT = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"
ASSET_ROSTER = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
ROUTES = (
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SPCX",
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hulk_expansion_bidirectional_tuned_v2|ETH",
    "hulk_expansion_bidirectional_tuned_v2|HYPE",
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE",
    "hype_breakout_onset_bidirectional_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|SOL",
    "hypervelocity_source_follow_bidirectional_5m_v1|BTC",
)
MAXIMUM_CHECKPOINT_AGE_SECONDS = 90.0
_SIDES = frozenset({"long", "short"})


def require_exact_config(config: MultiAssetLiveConfig) -> tuple[str, ...]:
    """Require the immutable v39 fingerprint, assets, routes, and authority shape."""
    routes = tuple(
        sorted(
            f"{provider}|{symbol}"
            for provider, symbol in config.executable_provider_symbols
        )
    )
    exact = (
        config.profile_id == PROFILE_ID
        and config.profile_fingerprint == PROFILE_FINGERPRINT
        and config.symbols == ASSET_ROSTER
        and routes == ROUTES
        and len(config.providers) == 7
        and len(config.executable_provider_directions) == 28
        and config.maximum_positions == 10
        and all(
            provider.execution_symbols == provider.symbols and provider.sides == _SIDES
            for provider in config.providers
        )
    )
    if not exact:
        raise ValueError("v39 forward evidence requires the exact v39 config")
    return ROUTES


def require_run_identity(
    run: Record,
    config: MultiAssetLiveConfig,
    expected: tuple[str, ...],
) -> None:
    """Require the checkpoint run to match the frozen v39 configuration."""
    matches = (
        run.get("profile_id") == config.profile_id
        and run.get("profile_fingerprint") == config.profile_fingerprint
        and _text_set(run.get("executable_provider_symbols"), "run routes")
        == set(expected)
        and _text_list(run.get("observe_only_provider_symbols"), "observe routes") == []
        and _integer(run.get("maximum_concurrent_positions"), "position limit") == 10
    )
    if not matches:
        raise ValueError("v39 forward evidence profile identity does not match runtime")


def validated_source(
    run: Record,
    checkpoint: Record,
    observed_at: datetime,
) -> dict[str, object]:
    """Validate causal RFC3339 source times and bounded checkpoint freshness."""
    observed = _aware_datetime(observed_at, "monitor observation")
    last = _timestamp(run.get("last_observed_at_utc"), "last observed")
    generated = _timestamp(
        checkpoint.get("generated_at_utc"), "checkpoint generated time"
    )
    first_raw = run.get("first_observed_at_utc")
    first = None if first_raw is None else _timestamp(first_raw, "first observed")
    if last > generated or generated > observed or (first is not None and first > last):
        raise ValueError("source timestamps are not causal")
    checkpoint_age = (observed - generated).total_seconds()
    observation_age = (observed - last).total_seconds()
    if checkpoint_age > MAXIMUM_CHECKPOINT_AGE_SECONDS:
        raise ValueError("checkpoint is stale")
    if observation_age > MAXIMUM_CHECKPOINT_AGE_SECONDS:
        raise ValueError("source observation is stale")
    return _source_payload(run, first, last, generated, checkpoint_age, observation_age)


def _source_payload(
    run: Record,
    first: datetime | None,
    last: datetime,
    generated: datetime,
    checkpoint_age: float,
    observation_age: float,
) -> dict[str, object]:
    return {
        "run_id": _text(run.get("run_id"), "run id"),
        "profile_id": _text(run.get("profile_id"), "profile id"),
        "profile_fingerprint": _text(run.get("profile_fingerprint"), "fingerprint"),
        "first_observed_at_utc": None if first is None else first.isoformat(),
        "last_observed_at_utc": last.isoformat(),
        "checkpoint_generated_at_utc": generated.isoformat(),
        "freshness": {
            "status": "fresh",
            "age_seconds": max(checkpoint_age, observation_age),
            "checkpoint_age_seconds": checkpoint_age,
            "source_observation_age_seconds": observation_age,
            "maximum_age_seconds": MAXIMUM_CHECKPOINT_AGE_SECONDS,
        },
    }


def _timestamp(value: object, label: str) -> datetime:
    raw = _text(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 timestamp") from exc
    return _aware_datetime(parsed, label)


def _aware_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value.astimezone(UTC)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text array")
    return list(value)


def _text_set(value: object, label: str) -> set[str]:
    items = _text_list(value, label)
    unique = set(items)
    if len(unique) != len(items):
        raise ValueError(f"{label} contains duplicate route identity")
    return unique


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
