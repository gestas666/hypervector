"""Strict configuration for the rebuilt Hulk Smash BTC canary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import tomllib
from typing import Literal, cast

from hypervector.research.market_cipher_strategy_research import (
    resolve_hulk_research_profile,
)

HulkExecutionMode = Literal["observe", "live"]

_ROOT_KEYS = frozenset(
    {"profile", "symbol", "strategy_id", "venue", "risk", "signal", "exit", "runtime"}
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
            "risk_fraction",
            "maximum_portfolio_risk_fraction",
            "max_notional_usd",
            "max_positions_per_symbol",
        }
    ),
    "signal": frozenset(
        {
            "source_timeframe",
            "signal_timeframe",
            "lookback_days",
            "minimum_score",
            "pivot_bars",
            "supertrend_period",
            "supertrend_multiplier",
            "adx_period",
            "squeeze_period",
            "adx_usable",
            "adx_trending",
            "backtest_lab_root",
            "backtest_lab_tree_sha256",
        }
    ),
    "exit": frozenset(
        {
            "minimum_stop_bps",
            "maximum_stop_bps",
            "target_r_multiple",
            "maximum_hold_bars",
        }
    ),
    "runtime": frozenset(
        {
            "backend_ledger",
            "stop_file",
            "maximum_entry_delay_seconds",
            "markout_horizon_ms",
            "capital_source",
            "portfolio_purpose",
            "metalabel_mode",
        }
    ),
}


class HulkSmashLiveConfigError(ValueError):
    """The Hulk canary configuration or requested authority is invalid."""


@dataclass(frozen=True)
class HulkSmashLiveConfig:
    """One immutable observe-only or explicitly armed BTC canary contract."""

    profile_id: str
    symbol: str
    strategy_id: str
    network: str
    margin_mode: str
    leverage: float
    venue_max_leverage: float
    market_slippage_cap_fraction: float
    risk_fraction: float
    maximum_portfolio_risk_fraction: float
    max_notional_usd: float
    max_positions_per_symbol: int
    source_timeframe: str
    signal_timeframe: str
    lookback_days: int
    minimum_score: int
    pivot_bars: int
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    adx_usable: float
    adx_trending: float
    backtest_lab_root: Path
    backtest_lab_tree_sha256: str
    minimum_stop_bps: float
    maximum_stop_bps: float
    target_r_multiple: float
    maximum_hold_bars: int
    backend_ledger: Path
    stop_file: Path
    maximum_entry_delay_seconds: int
    markout_horizon_ms: int
    capital_source: str
    portfolio_purpose: str
    metalabel_mode: str
    mode: HulkExecutionMode
    enabled: bool
    accepts_live_risk: bool

    @property
    def profile_fingerprint(self) -> str:
        """Hash the complete stable strategy contract without arm state."""
        values = asdict(self)
        for key in ("mode", "enabled", "accepts_live_risk"):
            values.pop(key)
        return _fingerprint(values)

    @property
    def run_fingerprint(self) -> str:
        """Hash stable identity plus requested execution authority."""
        return _fingerprint(
            {
                "profile_fingerprint": self.profile_fingerprint,
                "mode": self.mode,
                "enabled": self.enabled,
                "accepts_live_risk": self.accepts_live_risk,
            }
        )

    @property
    def maximum_hold_seconds(self) -> int:
        """Return the 30-minute-bar hold bound in seconds."""
        return self.maximum_hold_bars * 30 * 60

    def effective_arm_state(self, *, credentials_present: bool) -> str:
        """Return the backend-confirmable authority label."""
        if self.mode == "live" and self.enabled and self.accepts_live_risk:
            return "LIVE ARMED" if credentials_present else "DISARMED"
        return "DISARMED"

    def require_live_start(self, *, credentials_present: bool) -> None:
        """Fail closed unless live mode, both flags, and credentials are present."""
        if self.mode != "live":
            raise HulkSmashLiveConfigError("live start refused in observe mode")
        if not self.enabled:
            raise HulkSmashLiveConfigError("live start requires --enabled")
        if not self.accepts_live_risk:
            raise HulkSmashLiveConfigError("live start requires --i-accept-live-risk")
        if not credentials_present:
            raise HulkSmashLiveConfigError(
                "live start requires configured Hyperliquid credentials"
            )


def load_hulk_smash_live_config(
    path: Path | str,
    *,
    mode: HulkExecutionMode,
    enabled: bool = False,
    accepts_live_risk: bool = False,
) -> HulkSmashLiveConfig:
    """Load and validate the one frozen Hulk canary profile."""
    if mode not in {"observe", "live"}:
        raise HulkSmashLiveConfigError("Hulk mode must be observe or live")
    if mode == "observe" and (enabled or accepts_live_risk):
        raise HulkSmashLiveConfigError("observe mode cannot accept live flags")
    config_path = Path(path)
    raw = _load_toml(config_path)
    sections = _validated_sections(raw)
    config = _build_config(
        config_path,
        raw,
        sections,
        mode=mode,
        enabled=enabled,
        accepts_live_risk=accepts_live_risk,
    )
    _validate_frozen_contract(config)
    return config


def _validated_sections(
    raw: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    _reject_unknown(raw, _ROOT_KEYS, "root")
    sections = {name: _section(raw, name) for name in _SECTION_KEYS}
    for name, values in sections.items():
        _reject_unknown(values, _SECTION_KEYS[name], name)
    return sections


def _build_config(
    path: Path,
    raw: Mapping[str, object],
    sections: Mapping[str, Mapping[str, object]],
    *,
    mode: HulkExecutionMode,
    enabled: bool,
    accepts_live_risk: bool,
) -> HulkSmashLiveConfig:
    venue, risk = sections["venue"], sections["risk"]
    signal, exits, runtime = sections["signal"], sections["exit"], sections["runtime"]
    return HulkSmashLiveConfig(
        profile_id=_text(raw, "profile"),
        symbol=_text(raw, "symbol"),
        strategy_id=_text(raw, "strategy_id"),
        network=_text(venue, "network"),
        margin_mode=_text(venue, "margin_mode"),
        leverage=_number(venue, "leverage"),
        venue_max_leverage=_number(venue, "venue_max_leverage"),
        market_slippage_cap_fraction=_number(venue, "market_slippage_cap_fraction"),
        risk_fraction=_number(risk, "risk_fraction"),
        maximum_portfolio_risk_fraction=_number(
            risk, "maximum_portfolio_risk_fraction"
        ),
        max_notional_usd=_number(risk, "max_notional_usd"),
        max_positions_per_symbol=_integer(risk, "max_positions_per_symbol"),
        source_timeframe=_text(signal, "source_timeframe"),
        signal_timeframe=_text(signal, "signal_timeframe"),
        lookback_days=_integer(signal, "lookback_days"),
        minimum_score=_integer(signal, "minimum_score"),
        pivot_bars=_integer(signal, "pivot_bars"),
        supertrend_period=_integer(signal, "supertrend_period"),
        supertrend_multiplier=_number(signal, "supertrend_multiplier"),
        adx_period=_integer(signal, "adx_period"),
        squeeze_period=_integer(signal, "squeeze_period"),
        adx_usable=_number(signal, "adx_usable"),
        adx_trending=_number(signal, "adx_trending"),
        backtest_lab_root=_relative_path(path, _text(signal, "backtest_lab_root")),
        backtest_lab_tree_sha256=_text(signal, "backtest_lab_tree_sha256"),
        minimum_stop_bps=_number(exits, "minimum_stop_bps"),
        maximum_stop_bps=_number(exits, "maximum_stop_bps"),
        target_r_multiple=_number(exits, "target_r_multiple"),
        maximum_hold_bars=_integer(exits, "maximum_hold_bars"),
        backend_ledger=Path(_text(runtime, "backend_ledger")),
        stop_file=Path(_text(runtime, "stop_file")),
        maximum_entry_delay_seconds=_integer(runtime, "maximum_entry_delay_seconds"),
        markout_horizon_ms=_integer(runtime, "markout_horizon_ms"),
        capital_source=_text(runtime, "capital_source"),
        portfolio_purpose=_text(runtime, "portfolio_purpose"),
        metalabel_mode=_text(runtime, "metalabel_mode"),
        mode=mode,
        enabled=bool(enabled),
        accepts_live_risk=bool(accepts_live_risk),
    )


def _validate_frozen_contract(config: HulkSmashLiveConfig) -> None:
    expected_text = {
        "symbol": "BTC",
        "strategy_id": "hulk_expansion_short_robust_v3",
        "network": "mainnet",
        "margin_mode": "isolated",
        "source_timeframe": "5m",
        "signal_timeframe": "30m",
        "capital_source": "standalone_canary",
        "portfolio_purpose": "canary_validation",
        "metalabel_mode": "observe",
    }
    for name, expected in expected_text.items():
        if getattr(config, name) != expected:
            raise HulkSmashLiveConfigError(f"{name} must equal {expected!r}")
    _validate_numbers(config)
    _validate_paths(config)
    _validate_research_profile(config)


def _validate_numbers(config: HulkSmashLiveConfig) -> None:
    expected = {
        "leverage": 5.0,
        "venue_max_leverage": 40.0,
        "market_slippage_cap_fraction": 0.002,
        "risk_fraction": 0.0025,
        "maximum_portfolio_risk_fraction": 0.02,
        "max_notional_usd": 150.0,
        "minimum_stop_bps": 20.0,
        "maximum_stop_bps": 75.0,
        "target_r_multiple": 3.0,
    }
    for name, value in expected.items():
        if not math.isclose(float(getattr(config, name)), value):
            raise HulkSmashLiveConfigError(f"{name} must equal {value:g}")
    integer_expected = {
        "max_positions_per_symbol": 1,
        "minimum_score": 7,
        "pivot_bars": 6,
        "supertrend_period": 7,
        "adx_period": 20,
        "squeeze_period": 20,
        "maximum_hold_bars": 48,
        "maximum_entry_delay_seconds": 60,
        "markout_horizon_ms": 5_000,
    }
    for name, value in integer_expected.items():
        if getattr(config, name) != value:
            raise HulkSmashLiveConfigError(f"{name} must equal {value}")
    if config.risk_fraction > config.maximum_portfolio_risk_fraction:
        raise HulkSmashLiveConfigError("trade risk exceeds portfolio risk cap")


def _validate_paths(config: HulkSmashLiveConfig) -> None:
    if config.backend_ledger != Path("data/live/hulk_smash/decisions.jsonl"):
        raise HulkSmashLiveConfigError("backend_ledger must use the Hulk live path")
    if config.stop_file != Path("data/live/hulk_smash/STOP"):
        raise HulkSmashLiveConfigError("stop_file must use the Hulk live path")
    digest = config.backtest_lab_tree_sha256
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise HulkSmashLiveConfigError(
            "backtest_lab_tree_sha256 must be lowercase SHA-256"
        )


def _validate_research_profile(config: HulkSmashLiveConfig) -> None:
    profile = resolve_hulk_research_profile(config.strategy_id)
    expected = (
        profile.side,
        profile.supertrend_period,
        profile.supertrend_multiplier,
        profile.adx_period,
        profile.squeeze_period,
        profile.minimum_score,
        profile.pivot_bars,
        profile.adx_usable,
        profile.adx_trending,
    )
    observed = (
        "short",
        config.supertrend_period,
        config.supertrend_multiplier,
        config.adx_period,
        config.squeeze_period,
        config.minimum_score,
        config.pivot_bars,
        config.adx_usable,
        config.adx_trending,
    )
    if observed != expected:
        raise HulkSmashLiveConfigError("canary parameters differ from research profile")


def _load_toml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Hulk canary config not found: {path}")
    try:
        with path.open("rb") as handle:
            return cast(dict[str, object], tomllib.load(handle))
    except tomllib.TOMLDecodeError as exc:
        raise HulkSmashLiveConfigError(f"invalid Hulk TOML: {exc}") from exc


def _section(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, dict) or not all(isinstance(name, str) for name in value):
        raise HulkSmashLiveConfigError(f"{key} must be a TOML table")
    return cast(dict[str, object], value)


def _reject_unknown(
    values: Mapping[str, object], allowed: frozenset[str], label: str
) -> None:
    unknown = sorted(set(values).difference(allowed))
    if unknown:
        raise HulkSmashLiveConfigError(f"unknown {label} config fields: {unknown}")


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HulkSmashLiveConfigError(f"{key} must be non-empty text")
    return value.strip()


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HulkSmashLiveConfigError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise HulkSmashLiveConfigError(f"{key} must be positive and finite")
    return number


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HulkSmashLiveConfigError(f"{key} must be a positive integer")
    return value


def _relative_path(config_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (
        path.resolve() if path.is_absolute() else (config_path.parent / path).resolve()
    )


def _fingerprint(values: Mapping[str, object]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
