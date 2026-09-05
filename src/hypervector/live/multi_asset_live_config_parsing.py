"""Typed TOML parsing primitives for multi-asset live configuration."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
import tomllib
from typing import Literal, cast

_BOTH_SIDES = frozenset({"long", "short"})
_ENTRY_CONTEXT_POLICIES = frozenset({"dual_mtf_not_opposed"})
ProviderPositionPolicy = Literal["enter_and_close", "flat_entry_only"]


class MultiAssetLiveConfigError(ValueError):
    """The multi-asset profile or requested authority is invalid."""


def load_toml(path: Path) -> Mapping[str, object]:
    """Load one TOML mapping with a configuration-specific decode error."""
    if not path.is_file():
        raise FileNotFoundError(f"multi-asset config not found: {path}")
    try:
        with path.open("rb") as handle:
            return cast(dict[str, object], tomllib.load(handle))
    except tomllib.TOMLDecodeError as exc:
        raise MultiAssetLiveConfigError(f"invalid multi-asset TOML: {exc}") from exc


def mapping(value: object, label: str) -> Mapping[str, object]:
    """Require a string-keyed TOML table."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MultiAssetLiveConfigError(f"{label} must be a TOML table")
    return cast(dict[str, object], value)


def mapping_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    """Require one non-empty TOML table array."""
    if not isinstance(value, list) or not value:
        raise MultiAssetLiveConfigError(f"{label} must be a non-empty table array")
    return tuple(mapping(row, label) for row in value)


def text(values: Mapping[str, object], key: str) -> str:
    """Require one non-empty text field."""
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MultiAssetLiveConfigError(f"{key} must be non-empty text")
    return value.strip()


def number(values: Mapping[str, object], key: str) -> float:
    """Require one positive finite numeric field."""
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAssetLiveConfigError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise MultiAssetLiveConfigError(f"{key} must be positive and finite")
    return result


def optional_number(values: Mapping[str, object], key: str) -> float | None:
    """Parse one optional positive finite numeric field."""
    if key not in values:
        return None
    return number(values, key)


def integer(values: Mapping[str, object], key: str) -> int:
    """Require one positive integer field."""
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MultiAssetLiveConfigError(f"{key} must be a positive integer")
    return value


def strings(value: object, label: str) -> tuple[str, ...]:
    """Require one non-empty list of non-empty text values."""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise MultiAssetLiveConfigError(f"{label} must be non-empty text values")
    return tuple(str(item).strip() for item in value)


def optional_strings(value: object, label: str) -> tuple[str, ...]:
    """Parse a possibly empty list of text values."""
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise MultiAssetLiveConfigError(f"{label} must be a text list")
    return tuple(str(item).strip() for item in value)


def optional_path(value: object) -> Path | None:
    """Parse an optional non-empty source profile path."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MultiAssetLiveConfigError("source_profile must be non-empty text")
    return Path(value.strip())


def provider_position_policy(value: object) -> ProviderPositionPolicy:
    """Parse an explicit interaction policy or the legacy close-capable default."""
    if value is None:
        return "enter_and_close"
    if value not in {"enter_and_close", "flat_entry_only"}:
        raise MultiAssetLiveConfigError("provider position_policy is unsupported")
    return cast(ProviderPositionPolicy, value)


def side_overrides(value: object) -> tuple[tuple[str, frozenset[str]], ...]:
    """Parse normalized provider-symbol direction restrictions."""
    if value is None:
        return ()
    rows = mapping(value, "provider execution_side_overrides")
    overrides = tuple(
        (symbol.strip(), sides(sides_value, "provider execution side override"))
        for symbol, sides_value in rows.items()
    )
    symbols = [symbol for symbol, _ in overrides]
    if not all(symbols) or len(set(symbols)) != len(symbols):
        raise MultiAssetLiveConfigError(
            "provider execution_side_overrides symbols must be unique text"
        )
    return overrides


def entry_context_overrides(value: object) -> tuple[tuple[str, str], ...]:
    """Parse explicit provider-symbol entry-context policies."""
    if value is None:
        return ()
    rows = mapping(value, "provider entry_context_overrides")
    overrides: list[tuple[str, str]] = []
    for symbol, raw_policy in rows.items():
        if not symbol.strip() or not isinstance(raw_policy, str):
            raise MultiAssetLiveConfigError(
                "provider entry_context_overrides must map symbols to policies"
            )
        policy = raw_policy.strip()
        if policy not in _ENTRY_CONTEXT_POLICIES:
            raise MultiAssetLiveConfigError(
                "provider entry_context_overrides contains an unsupported policy"
            )
        overrides.append((symbol.strip(), policy))
    return tuple(overrides)


def positive_number_overrides(
    value: object,
    label: str,
) -> tuple[tuple[str, float], ...]:
    """Parse a symbol-keyed table of positive finite numbers."""
    if value is None:
        return ()
    rows = mapping(value, label)
    overrides = tuple(
        (symbol.strip(), _positive_number(raw, label)) for symbol, raw in rows.items()
    )
    symbols = [symbol for symbol, _ in overrides]
    if not all(symbols) or any(raw <= 0.0 for _, raw in overrides):
        raise MultiAssetLiveConfigError(f"{label} must map symbols to positive numbers")
    return overrides


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAssetLiveConfigError(f"{label} values must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise MultiAssetLiveConfigError(f"{label} values must be positive and finite")
    return result


def sides(value: object, label: str) -> frozenset[str]:
    """Require one non-empty subset of the supported directions."""
    result = frozenset(strings(value, label))
    if not result.issubset(_BOTH_SIDES):
        raise MultiAssetLiveConfigError(f"{label} must contain long and/or short")
    return result


def require_live_start(
    *,
    mode: str,
    enabled: bool,
    accepts_live_risk: bool,
    credentials_present: bool,
) -> None:
    """Reject a live start unless authority and credentials are explicit."""
    if mode != "live":
        raise MultiAssetLiveConfigError("live start refused because mode is observe")
    if not enabled:
        raise MultiAssetLiveConfigError("live start requires --enabled")
    if not accepts_live_risk:
        raise MultiAssetLiveConfigError("live start requires --i-accept-live-risk")
    if not credentials_present:
        raise MultiAssetLiveConfigError("live start requires configured credentials")
