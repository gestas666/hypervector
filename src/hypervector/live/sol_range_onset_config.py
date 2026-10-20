"""Strict, fail-closed configuration for SOL range-onset canary runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import tomllib
from typing import Literal, Mapping, cast

from hypervector.research.sol_range_onset_shadow_models import SolShadowConfig

SolExecutionMode = Literal["shadow", "live"]

_ROOT_KEYS = frozenset(
    {"profile", "symbol", "strategy_id", "venue", "risk", "exit", "runtime"}
)
_SECTION_KEYS = {
    "venue": frozenset(
        {
            "network",
            "margin_mode",
            "leverage",
            "venue_max_leverage",
            "market_slippage_cap_fraction",
        }
    ),
    "risk": frozenset(
        {
            "initial_shadow_equity_usd",
            "margin_fraction",
            "max_notional_usd",
            "max_positions_per_symbol",
        }
    ),
    "exit": frozenset({"stop_bps", "maximum_hold_seconds"}),
    "runtime": frozenset(
        {
            "backend_ledger",
            "shadow_ledger",
            "live_ledger",
            "stop_file",
            "live_stop_file",
            "capital_source",
            "portfolio_purpose",
            "metalabel_mode",
        }
    ),
}


class SolCanaryConfigError(ValueError):
    """The SOL canary profile or requested authority state is invalid."""


@dataclass(frozen=True)
class SolRangeOnsetConfig:
    """One validated shadow or fail-closed live SOL run configuration."""

    profile_id: str
    symbol: str
    strategy_id: str
    network: str
    margin_mode: str
    leverage: float
    venue_max_leverage: float
    market_slippage_cap_fraction: float
    initial_shadow_equity_usd: float
    margin_fraction: float
    max_notional_usd: float
    max_positions_per_symbol: int
    stop_bps: float
    maximum_hold_seconds: int
    backend_ledger: Path
    shadow_ledger: Path
    live_ledger: Path
    stop_file: Path
    live_stop_file: Path
    capital_source: str
    portfolio_purpose: str
    metalabel_mode: str
    mode: SolExecutionMode
    enabled: bool
    accepts_live_risk: bool

    @property
    def effective_entry_slippage_cap_fraction(self) -> float:
        """Expose the legacy opening cap to shared pre-entry risk calculations."""
        return self.market_slippage_cap_fraction

    @property
    def profile_fingerprint(self) -> str:
        """Hash stable strategy, risk, venue, and ledger settings."""
        payload = asdict(self)
        payload.pop("mode")
        payload.pop("enabled")
        payload.pop("accepts_live_risk")
        return _fingerprint(payload)

    @property
    def run_fingerprint(self) -> str:
        """Hash the profile plus requested execution mode without secrets."""
        return _fingerprint(
            {
                "profile_fingerprint": self.profile_fingerprint,
                "mode": self.mode,
            }
        )

    def effective_arm_state(self, *, credentials_present: bool) -> str:
        """Return the backend-confirmable authority state for display."""
        if self.mode == "shadow":
            return "SHADOW"
        if self.enabled and self.accepts_live_risk and credentials_present:
            return "LIVE ARMED"
        return "DISARMED"

    @property
    def authoritative_ledger(self) -> Path:
        """Return the only ledger the TUI may consume for this mode."""
        return self.live_ledger if self.mode == "live" else self.backend_ledger

    @property
    def authoritative_stop_file(self) -> Path:
        """Return the STOP path owned by the selected execution mode."""
        return self.live_stop_file if self.mode == "live" else self.stop_file

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Reject live startup unless every independent authority condition holds."""
        if self.mode != "live":
            raise SolCanaryConfigError("live start refused because mode is shadow")
        if not self.enabled:
            raise SolCanaryConfigError("live start requires --enabled")
        if not self.accepts_live_risk:
            raise SolCanaryConfigError("live start requires --i-accept-live-risk")
        if not credentials_present:
            raise SolCanaryConfigError(
                "live start requires configured Hyperliquid credentials"
            )

    def shadow_engine_config(self) -> SolShadowConfig:
        """Translate the canary profile into the no-submit lifecycle contract."""
        return SolShadowConfig(
            initial_shared_equity_usd=self.initial_shadow_equity_usd,
            capital_base_cap_usd=self.initial_shadow_equity_usd,
            notional_cap_usd=self.max_notional_usd,
            margin_fraction=self.margin_fraction,
            leverage=self.leverage,
            venue_max_leverage=self.venue_max_leverage,
            stop_bps=self.stop_bps,
            max_hold_ms=self.maximum_hold_seconds * 1_000,
        )


def load_sol_range_onset_config(
    path: Path | str,
    *,
    mode: SolExecutionMode,
    enabled: bool = False,
    accepts_live_risk: bool = False,
) -> SolRangeOnsetConfig:
    """Load one strict profile and bind an explicit shadow/live request."""
    if mode not in {"shadow", "live"}:
        raise SolCanaryConfigError("SOL execution mode must be shadow or live")
    raw = _load_toml(Path(path))
    _reject_unknown(raw, _ROOT_KEYS, "root")
    venue = _section(raw, "venue")
    risk = _section(raw, "risk")
    exits = _section(raw, "exit")
    runtime = _section(raw, "runtime")
    for name, section in (
        ("venue", venue),
        ("risk", risk),
        ("exit", exits),
        ("runtime", runtime),
    ):
        _reject_unknown(section, _SECTION_KEYS[name], name)
    config = SolRangeOnsetConfig(
        profile_id=_text(raw, "profile"),
        symbol=_text(raw, "symbol"),
        strategy_id=_text(raw, "strategy_id"),
        network=_text(venue, "network"),
        margin_mode=_text(venue, "margin_mode"),
        leverage=_positive_number(venue, "leverage"),
        venue_max_leverage=_positive_number(venue, "venue_max_leverage"),
        market_slippage_cap_fraction=_positive_number(
            venue,
            "market_slippage_cap_fraction",
        ),
        initial_shadow_equity_usd=_positive_number(risk, "initial_shadow_equity_usd"),
        margin_fraction=_positive_number(risk, "margin_fraction"),
        max_notional_usd=_positive_number(risk, "max_notional_usd"),
        max_positions_per_symbol=_positive_integer(risk, "max_positions_per_symbol"),
        stop_bps=_positive_number(exits, "stop_bps"),
        maximum_hold_seconds=_positive_integer(exits, "maximum_hold_seconds"),
        backend_ledger=Path(_text(runtime, "backend_ledger")),
        shadow_ledger=Path(_text(runtime, "shadow_ledger")),
        live_ledger=Path(_text(runtime, "live_ledger")),
        stop_file=Path(_text(runtime, "stop_file")),
        live_stop_file=Path(_text(runtime, "live_stop_file")),
        capital_source=_text(runtime, "capital_source"),
        portfolio_purpose=_text(runtime, "portfolio_purpose"),
        metalabel_mode=_text(runtime, "metalabel_mode"),
        mode=mode,
        enabled=bool(enabled),
        accepts_live_risk=bool(accepts_live_risk),
    )
    _validate_frozen_profile(config)
    return config


def _validate_frozen_profile(config: SolRangeOnsetConfig) -> None:
    expected_text = {
        "symbol": "SOL",
        "strategy_id": "sol_1h_sma10x30_5m_range_or_breakout",
        "network": "mainnet",
        "margin_mode": "isolated",
        "capital_source": "standalone_canary",
        "portfolio_purpose": "canary_validation",
        "metalabel_mode": "off",
    }
    for name, expected in expected_text.items():
        if getattr(config, name) != expected:
            raise SolCanaryConfigError(f"{name} must be {expected!r}")
    if config.leverage > config.venue_max_leverage:
        raise SolCanaryConfigError("leverage must not exceed venue_max_leverage")
    if config.margin_fraction > 1.0:
        raise SolCanaryConfigError("margin_fraction must not exceed one")
    expected_numbers = {
        "leverage": 5.0,
        "venue_max_leverage": 20.0,
        "market_slippage_cap_fraction": 0.01,
        "initial_shadow_equity_usd": 150.0,
        "margin_fraction": 0.03,
        "max_notional_usd": 22.5,
        "stop_bps": 80.0,
        "maximum_hold_seconds": 172_800.0,
    }
    for name, expected in expected_numbers.items():
        if not math.isclose(float(getattr(config, name)), expected):
            raise SolCanaryConfigError(
                f"{name} must equal the frozen value {expected:g}"
            )
    if config.max_positions_per_symbol != 1:
        raise SolCanaryConfigError("SOL canary permits exactly one position per symbol")
    ledgers = {config.backend_ledger, config.shadow_ledger, config.live_ledger}
    if len(ledgers) != 3:
        raise SolCanaryConfigError(
            "backend, shadow, and live ledgers must be different paths"
        )
    stop_files = {config.stop_file, config.live_stop_file}
    if len(stop_files) != 2:
        raise SolCanaryConfigError("shadow and live STOP files must be different paths")
    for path in (*ledgers, *stop_files):
        if "sol_range_onset_canary" not in path.parts:
            raise SolCanaryConfigError(
                "canary ledger paths must use sol_range_onset_canary"
            )
    if "live" not in config.live_ledger.parts:
        raise SolCanaryConfigError("live_ledger must be stored under a live directory")
    if "live" not in config.live_stop_file.parts:
        raise SolCanaryConfigError(
            "live_stop_file must be stored under a live directory"
        )


def _load_toml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"SOL canary config not found: {path}")
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SolCanaryConfigError(f"invalid SOL canary TOML: {exc}") from exc
    return cast(dict[str, object], value)


def _section(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, dict) or not all(isinstance(name, str) for name in value):
        raise SolCanaryConfigError(f"{key} must be a TOML table")
    return cast(dict[str, object], value)


def _reject_unknown(
    values: Mapping[str, object], allowed: frozenset[str], label: str
) -> None:
    unknown = sorted(set(values).difference(allowed))
    if unknown:
        raise SolCanaryConfigError(f"unknown {label} config fields: {unknown}")


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SolCanaryConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _positive_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SolCanaryConfigError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise SolCanaryConfigError(f"{key} must be positive and finite")
    return number


def _positive_integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SolCanaryConfigError(f"{key} must be a positive integer")
    return value


def _fingerprint(values: Mapping[str, object]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
