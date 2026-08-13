"""Strict fail-closed configuration for the Apex MM measurement canary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import tomllib


_ROOT_KEYS = frozenset(
    {"profile", "strategy_id", "symbol", "venue", "risk", "execution", "live"}
)
_SECTION_KEYS = {
    "venue": frozenset({"network", "margin_mode", "expected_max_leverage", "leverage"}),
    "risk": frozenset(
        {
            "base_order_notional_usd",
            "max_inventory_notional_usd",
            "max_positions_per_symbol",
        }
    ),
    "execution": frozenset(
        {
            "quote_refresh_ms",
            "minimum_order_notional_usd",
            "maximum_book_age_ms",
            "markout_horizon_ms",
            "depth_levels",
        }
    ),
    "live": frozenset(
        {"backend_ledger", "stop_file", "capital_source", "portfolio_purpose"}
    ),
}


class ApexMMLiveConfigError(ValueError):
    """The Apex MM live wrapper is invalid or not armed."""


@dataclass(frozen=True)
class ApexMMLiveConfig:
    """One explicit mainnet binding for a small execution measurement canary."""

    profile_id: str
    strategy_id: str
    symbol: str
    network: str
    margin_mode: str
    expected_max_leverage: int
    leverage: int
    base_order_notional_usd: float
    max_inventory_notional_usd: float
    max_positions_per_symbol: int
    minimum_order_notional_usd: float
    quote_refresh_ms: int
    maximum_book_age_ms: int
    markout_horizon_ms: int
    depth_levels: int
    backend_ledger: Path
    stop_file: Path
    capital_source: str
    portfolio_purpose: str
    enabled: bool
    accepts_live_risk: bool

    @property
    def profile_fingerprint(self) -> str:
        """Hash the stable secret-free strategy and venue contract."""
        return _fingerprint(self._identity())

    @property
    def run_fingerprint(self) -> str:
        """Hash the stable profile plus the requested runtime arm state."""
        return _fingerprint(
            {
                "profile_fingerprint": self.profile_fingerprint,
                "enabled": self.enabled,
                "accepts_live_risk": self.accepts_live_risk,
            }
        )

    @property
    def execution_authority(self) -> str:
        """Return requested authority; credential validation remains separate."""
        if self.enabled and self.accepts_live_risk:
            return "hyperliquid_mainnet"
        return "none"

    def effective_arm_state(self, *, credentials_present: bool) -> str:
        """Return the backend-confirmable authority state."""
        if self.enabled and self.accepts_live_risk and credentials_present:
            return "LIVE ARMED"
        return "DISARMED"

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Fail closed unless flags and credentials are all present."""
        if not self.enabled:
            raise ApexMMLiveConfigError("live start requires --enabled")
        if not self.accepts_live_risk:
            raise ApexMMLiveConfigError("live start requires --i-accept-live-risk")
        if not credentials_present:
            raise ApexMMLiveConfigError(
                "live start requires configured Hyperliquid credentials"
            )

    def _identity(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "network": self.network,
            "margin_mode": self.margin_mode,
            "expected_max_leverage": self.expected_max_leverage,
            "leverage": self.leverage,
            "base_order_notional_usd": self.base_order_notional_usd,
            "max_inventory_notional_usd": self.max_inventory_notional_usd,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "minimum_order_notional_usd": self.minimum_order_notional_usd,
            "quote_refresh_ms": self.quote_refresh_ms,
            "maximum_book_age_ms": self.maximum_book_age_ms,
            "markout_horizon_ms": self.markout_horizon_ms,
            "depth_levels": self.depth_levels,
            "backend_ledger": str(self.backend_ledger),
            "stop_file": str(self.stop_file),
            "capital_source": self.capital_source,
            "portfolio_purpose": self.portfolio_purpose,
        }


def load_apex_mm_live_config(
    path: Path | str,
    *,
    enabled: bool = False,
    accepts_live_risk: bool = False,
) -> ApexMMLiveConfig:
    """Load and validate the exact Apex MM canary without constructing clients."""
    raw = _load_toml(Path(path))
    _reject_unknown(raw, _ROOT_KEYS, "root")
    venue = _section(raw, "venue")
    risk = _section(raw, "risk")
    execution = _section(raw, "execution")
    live = _section(raw, "live")
    for name, values in (
        ("venue", venue),
        ("risk", risk),
        ("execution", execution),
        ("live", live),
    ):
        _reject_unknown(values, _SECTION_KEYS[name], name)
    config = ApexMMLiveConfig(
        profile_id=_text(raw, "profile"),
        strategy_id=_text(raw, "strategy_id"),
        symbol=_text(raw, "symbol"),
        network=_text(venue, "network"),
        margin_mode=_text(venue, "margin_mode"),
        expected_max_leverage=_positive_integer(venue, "expected_max_leverage"),
        leverage=_positive_integer(venue, "leverage"),
        base_order_notional_usd=_positive_number(risk, "base_order_notional_usd"),
        max_inventory_notional_usd=_positive_number(risk, "max_inventory_notional_usd"),
        max_positions_per_symbol=_positive_integer(risk, "max_positions_per_symbol"),
        minimum_order_notional_usd=_positive_number(
            execution, "minimum_order_notional_usd"
        ),
        quote_refresh_ms=_positive_integer(execution, "quote_refresh_ms"),
        maximum_book_age_ms=_nonnegative_integer(execution, "maximum_book_age_ms"),
        markout_horizon_ms=_positive_integer(execution, "markout_horizon_ms"),
        depth_levels=_positive_integer(execution, "depth_levels"),
        backend_ledger=Path(_text(live, "backend_ledger")),
        stop_file=Path(_text(live, "stop_file")),
        capital_source=_text(live, "capital_source"),
        portfolio_purpose=_text(live, "portfolio_purpose"),
        enabled=bool(enabled),
        accepts_live_risk=bool(accepts_live_risk),
    )
    _validate_frozen_contract(config)
    return config


def _validate_frozen_contract(config: ApexMMLiveConfig) -> None:
    expected: dict[str, object] = {
        "profile_id": "apex_regime_mm_canary_v1",
        "strategy_id": "apex_regime_mm_v2",
        "symbol": "BTC",
        "network": "mainnet",
        "margin_mode": "isolated",
        "expected_max_leverage": 40,
        "leverage": 3,
        "max_positions_per_symbol": 1,
        "minimum_order_notional_usd": 10.0,
        "capital_source": "standalone_canary",
        "portfolio_purpose": "execution_friction_measurement",
    }
    for name, value in expected.items():
        if getattr(config, name) != value:
            raise ApexMMLiveConfigError(f"{name} must equal {value!r}")
    if config.max_inventory_notional_usd < 2 * config.base_order_notional_usd:
        raise ApexMMLiveConfigError("inventory cap must cover at least two base orders")
    if config.base_order_notional_usd < config.minimum_order_notional_usd:
        raise ApexMMLiveConfigError("base order must meet the venue minimum notional")
    parent = Path("data/live/apex_regime_mm")
    if config.backend_ledger != parent / "decisions.jsonl":
        raise ApexMMLiveConfigError("backend_ledger must use the Apex MM live path")
    if config.stop_file != parent / "STOP":
        raise ApexMMLiveConfigError("stop_file must use the Apex MM live path")


def _load_toml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Apex MM live config not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _section(raw: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ApexMMLiveConfigError(f"{name} must be a table")
    return value


def _reject_unknown(
    values: Mapping[str, object],
    allowed: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(set(values).difference(allowed))
    if unknown:
        raise ApexMMLiveConfigError(f"unknown {label} keys: {unknown}")


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApexMMLiveConfigError(f"{key} must be non-empty text")
    return value.strip()


def _positive_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApexMMLiveConfigError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ApexMMLiveConfigError(f"{key} must be positive and finite")
    return number


def _positive_integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApexMMLiveConfigError(f"{key} must be a positive integer")
    return value


def _nonnegative_integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApexMMLiveConfigError(f"{key} must be a non-negative integer")
    return value


def _fingerprint(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
