"""Strict live-canary wrapper for the selected BTC 5m source-follow profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tomllib

from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
    load_source_follow_profile,
)
from hypervector.regime.source_follow_runtime import SourceDirectionMode

_PROFILE_DIRECTIONS = {
    "hypervelocity_source_follow_minrange12_alloc35_live_canary_v1": (
        "source_follow_short"
    ),
    "hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1": (
        "source_follow_bidirectional"
    ),
}
_ROOT_KEYS = frozenset({"profile", "strategy_profile", "venue", "risk", "live"})
_SECTION_KEYS = {
    "venue": frozenset({"network", "margin_mode", "expected_max_leverage"}),
    "risk": frozenset({"max_notional_usd", "max_positions_per_symbol"}),
    "live": frozenset(
        {"backend_ledger", "stop_file", "capital_source", "portfolio_purpose"}
    ),
}


class SourceFollowLiveConfigError(ValueError):
    """The selected source-follow live wrapper is invalid or not armed."""


@dataclass(frozen=True)
class SourceFollowLiveConfig:
    """One explicit mainnet canary binding around the measured strategy profile."""

    profile_id: str
    profile: SourceFollowHypervelocityProfile
    network: str
    margin_mode: str
    expected_max_leverage: int
    max_notional_usd: float
    max_positions_per_symbol: int
    backend_ledger: Path
    stop_file: Path
    capital_source: str
    portfolio_purpose: str
    enabled: bool
    accepts_live_risk: bool

    @property
    def symbol(self) -> str:
        """Return the inherited venue symbol."""
        return self.profile.symbol

    @property
    def signal_timeframe(self) -> str:
        """Return the completed-bar timeframe that owns entry decisions."""
        return str(self.profile.regime_policy()["primary_timeframe"])

    @property
    def context_timeframe(self) -> str:
        """Return the annotation-only higher timeframe."""
        return str(self.profile.regime_policy()["context_timeframe"])

    @property
    def leverage(self) -> float:
        """Return inherited isolated leverage."""
        return self.profile.leverage

    @property
    def margin_fraction(self) -> float:
        """Return inherited account-equity margin allocation."""
        return self.profile.margin_fraction

    @property
    def target_margin_pct(self) -> float:
        """Return the inherited gross margin target."""
        return self.profile.target_margin_pct

    @property
    def entry_ttl_seconds(self) -> float:
        """Return the inherited maker-entry lifetime."""
        return self.profile.entry_ttl_seconds

    @property
    def maximum_hold_seconds(self) -> float:
        """Return the inherited bounded holding period."""
        return self.profile.maximum_hold_seconds

    @property
    def runtime_direction_mode(self) -> SourceDirectionMode:
        """Translate the immutable profile mode into the runtime policy mode."""
        if self.profile.direction_mode == "source_follow_bidirectional":
            return "trend_bidirectional"
        return "short_only"

    @property
    def profile_fingerprint(self) -> str:
        """Hash all stable live and strategy identities without secrets."""
        return _fingerprint(self._identity())

    @property
    def run_fingerprint(self) -> str:
        """Hash stable identity plus the explicitly requested arm state."""
        return _fingerprint(
            {
                "profile_fingerprint": self.profile_fingerprint,
                "enabled": self.enabled,
                "accepts_live_risk": self.accepts_live_risk,
            }
        )

    def effective_arm_state(self, *, credentials_present: bool) -> str:
        """Return the backend-confirmable live authority state."""
        if self.enabled and self.accepts_live_risk and credentials_present:
            return "LIVE ARMED"
        return "DISARMED"

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Fail closed unless both operator flags and credentials are present."""
        if not self.enabled:
            raise SourceFollowLiveConfigError("live start requires --enabled")
        if not self.accepts_live_risk:
            raise SourceFollowLiveConfigError(
                "live start requires --i-accept-live-risk"
            )
        if not credentials_present:
            raise SourceFollowLiveConfigError(
                "live start requires configured Hyperliquid credentials"
            )

    def _identity(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "strategy_profile": self.profile.profile_id,
            "base_profile_sha256": self.profile.base_profile_sha256,
            "source_revision": self.profile.source_revision,
            "resolved_strategy_contract": self._resolved_strategy_contract(),
            "network": self.network,
            "margin_mode": self.margin_mode,
            "expected_max_leverage": self.expected_max_leverage,
            "max_notional_usd": self.max_notional_usd,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "backend_ledger": str(self.backend_ledger),
            "stop_file": str(self.stop_file),
            "capital_source": self.capital_source,
            "portfolio_purpose": self.portfolio_purpose,
        }

    def _resolved_strategy_contract(self) -> dict[str, object]:
        profile = self.profile
        return {
            "position_policy": profile.position_policy(),
            "regime_policy": profile.regime_policy(),
            "risk": {
                "margin_fraction": profile.margin_fraction,
                "leverage": profile.leverage,
                "max_notional_usd": self.max_notional_usd,
            },
            "exits": {
                "target_margin_pct": profile.target_margin_pct,
                "maximum_hold_seconds": profile.maximum_hold_seconds,
                "range_policy": profile.open_position_range_policy,
            },
            "execution": {
                "entry_ttl_seconds": profile.entry_ttl_seconds,
                "maximum_event_age_ms": profile.execution_max_event_age_ms,
                "restart_queue_policy": profile.restart_queue_policy,
            },
            "costs": {
                "maker_fee_rate": profile.maker_fee_rate,
                "taker_fee_rate": profile.taker_fee_rate,
                "slippage_bps": profile.slippage_bps,
                "funding_refresh_seconds": profile.funding_refresh_seconds,
            },
            "metalabel_mode": profile.metalabel_mode,
        }


def load_source_follow_live_config(
    path: Path | str,
    *,
    enabled: bool = False,
    accepts_live_risk: bool = False,
) -> SourceFollowLiveConfig:
    """Load the exact canary wrapper without constructing an execution client."""
    config_path = Path(path)
    raw = _load_toml(config_path)
    _reject_unknown(raw, _ROOT_KEYS, "root")
    venue = _section(raw, "venue")
    risk = _section(raw, "risk")
    live = _section(raw, "live")
    for name, section in (("venue", venue), ("risk", risk), ("live", live)):
        _reject_unknown(section, _SECTION_KEYS[name], name)
    profile_path = _relative_path(config_path, _text(raw, "strategy_profile"))
    config = SourceFollowLiveConfig(
        profile_id=_text(raw, "profile"),
        profile=load_source_follow_profile(profile_path),
        network=_text(venue, "network"),
        margin_mode=_text(venue, "margin_mode"),
        expected_max_leverage=_positive_integer(venue, "expected_max_leverage"),
        max_notional_usd=_positive_number(risk, "max_notional_usd"),
        max_positions_per_symbol=_positive_integer(risk, "max_positions_per_symbol"),
        backend_ledger=Path(_text(live, "backend_ledger")),
        stop_file=Path(_text(live, "stop_file")),
        capital_source=_text(live, "capital_source"),
        portfolio_purpose=_text(live, "portfolio_purpose"),
        enabled=bool(enabled),
        accepts_live_risk=bool(accepts_live_risk),
    )
    _validate_frozen_contract(config)
    return config


def _validate_frozen_contract(config: SourceFollowLiveConfig) -> None:
    expected = {
        "network": "mainnet",
        "margin_mode": "isolated",
        "capital_source": "standalone_canary",
        "portfolio_purpose": "canary_validation",
    }
    for name, value in expected.items():
        if getattr(config, name) != value:
            raise SourceFollowLiveConfigError(f"{name} must equal {value!r}")
    expected_direction = _PROFILE_DIRECTIONS.get(config.profile_id)
    if expected_direction is None:
        raise SourceFollowLiveConfigError(
            f"unsupported live profile_id: {config.profile_id!r}"
        )
    if config.profile.direction_mode != expected_direction:
        raise SourceFollowLiveConfigError(
            "live profile_id does not match strategy direction_mode"
        )
    if config.expected_max_leverage != 40:
        raise SourceFollowLiveConfigError("expected_max_leverage must equal 40")
    if config.max_notional_usd != 1_700.0:
        raise SourceFollowLiveConfigError("max_notional_usd must equal 1700")
    if config.max_positions_per_symbol != 1:
        raise SourceFollowLiveConfigError("max_positions_per_symbol must equal one")
    expected_parent = Path("data/live/hypervelocity_source_follow")
    if config.backend_ledger != expected_parent / "decisions.jsonl":
        raise SourceFollowLiveConfigError(
            "backend_ledger must use the canary live path"
        )
    if config.stop_file != expected_parent / "STOP":
        raise SourceFollowLiveConfigError("stop_file must use the canary live path")


def _load_toml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"source-follow live config not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _section(raw: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise SourceFollowLiveConfigError(f"{name} must be a table")
    return value


def _reject_unknown(
    values: Mapping[str, object],
    allowed: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise SourceFollowLiveConfigError(f"unknown {label} keys: {unknown}")


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceFollowLiveConfigError(f"{key} must be non-empty text")
    return value.strip()


def _positive_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceFollowLiveConfigError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise SourceFollowLiveConfigError(f"{key} must be positive and finite")
    return result


def _positive_integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceFollowLiveConfigError(f"{key} must be a positive integer")
    return value


def _relative_path(config_path: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else config_path.parent / candidate


def _fingerprint(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
