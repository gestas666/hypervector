"""Validated TOML runtime profile for faithful Hypervelocity shadow execution."""

from __future__ import annotations

import math
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping, cast

from hypervector.strategies.peak_observer_contract import (
    PeakObserverConfig,
)
from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    faithful_regime_config,
)


@dataclass(frozen=True)
class HypervelocityProfile:
    """Effective immutable and operational settings for one backend run."""

    profile_id: str
    symbol: str
    timeframe: str
    strategy_id: str
    position_mode: str
    max_positions_per_symbol: int
    direction_mode: str
    allow_reversal_while_open: bool
    switch_after_exit: bool
    margin_fraction: float
    leverage: float
    target_margin_pct: float
    open_position_range_policy: str
    margin_mode: Literal["isolated"]
    live_canary_max_notional_usd: float
    size_decimals: int
    venue_max_leverage: float
    fee_tier: int
    maker_fee_rate: float
    taker_fee_rate: float
    slippage_bps: float
    funding_refresh_seconds: float
    entry_ttl_seconds: float
    execution_submit_latency_ms: int
    execution_cancel_latency_ms: int
    execution_update_latency_ms: int
    execution_max_event_age_ms: int
    restart_queue_policy: Literal["requeue_behind_displayed_liquidity"]
    liquidation_execution_model: Literal["hyperliquid_market_liquidation_v2"]
    partial_liquidation_supported: bool
    partial_liquidation_threshold_usd: float
    partial_liquidation_fraction: float
    liquidation_cooldown_ms: int
    backstop_liquidation_supported: bool
    backstop_maintenance_fraction: float
    backstop_accounting_model: Literal["isolated_margin_transfer_composite_v1"]
    expired_entry_rearm_policy: str
    same_direction_reentry_policy: str
    reentry_cooldown_bars: int
    orderbook_archive_enabled: bool
    orderbook_archive_depth_levels: int
    runtime_mode: str
    shadow_execution_model: Literal["nautilus_event_v1"]
    initial_cash_usd: float
    export_path: Path
    lookback_days: int
    strict_hl_only: bool
    poll_interval_seconds: float
    metalabel_mode: str
    model_long_bundle: Path
    model_short_bundle: Path
    regime_config: RegimeClassifierConfig
    execution_timeframe: Literal["1m"]
    primary_timeframe: Literal["5m"]
    context_timeframe: Literal["15m"]
    context_is_hard_gate: bool
    allowed_entry_states: tuple[str, ...]
    blocked_entry_states: tuple[str, ...]
    breakout_requires_direction: bool
    confidence_is_gate: bool
    peak_observer: PeakObserverConfig

    def position_policy(self) -> dict[str, object]:
        """Return the effective position invariant for backend telemetry."""
        return {
            "position_mode": self.position_mode,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "direction_mode": self.direction_mode,
            "allow_reversal_while_open": self.allow_reversal_while_open,
            "switch_after_exit": self.switch_after_exit,
        }

    def regime_policy(self) -> dict[str, object]:
        """Return the validated point-in-time regime execution policy."""
        config = self.regime_config
        return {
            "execution_timeframe": self.execution_timeframe,
            "primary_timeframe": self.primary_timeframe,
            "context_timeframe": self.context_timeframe,
            "context_is_hard_gate": self.context_is_hard_gate,
            "entry_trigger": "5m_structure_or_confirmed_breakout",
            "tactical_setup": "bbwp_rsi_breakout_annotation",
            "tactical_setup_is_gate": False,
            "ema_fast": config.ema_fast,
            "ema_slow": config.ema_slow,
            "structure_lookback": config.structure_lookback,
            "minimum_trend_gap_bps": config.minimum_trend_gap_bps,
            "range_filter": "bbwp_compression",
            "bbwp_length": config.bbwp_length,
            "bbwp_lookback": config.bbwp_lookback,
            "bbwp_compression_threshold": config.bbwp_compression_threshold,
            "rsi_length": config.rsi_length,
            "rsi_signal_length": config.rsi_signal_length,
            "breakout_lookback": config.breakout_lookback,
            "breakout_clearance_bps": config.breakout_clearance_bps,
            "breakout_volume_lookback": config.breakout_volume_lookback,
            "breakout_volume_multiple": config.breakout_volume_multiple,
            "allowed_entry_states": list(self.allowed_entry_states),
            "blocked_entry_states": list(self.blocked_entry_states),
            "breakout_requires_direction": self.breakout_requires_direction,
            "confidence_is_gate": self.confidence_is_gate,
        }


def load_hypervelocity_profile(path: Path | str) -> HypervelocityProfile:
    """Load and fail-closed validate a faithful Hypervelocity TOML profile."""
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Hypervelocity config not found: {profile_path}")
    with profile_path.open("rb") as handle:
        raw = cast(dict[str, object], tomllib.load(handle))
    contract = HypervelocityContract()
    _validate_identity(raw)
    allocation = _section(raw, "allocation")
    exits = _section(raw, "exit")
    execution = _section(raw, "execution")
    entry = _section(raw, "entry")
    model = _section(raw, "model")
    peak_observer = _validated_peak_observer(_section(raw, "peak_observer"))
    runtime = _section(raw, "runtime")
    venue = _section(raw, "venue")
    costs = _section(raw, "costs")
    orderbook = _section(raw, "orderbook")
    _validate_contract(allocation, exits, execution, model, contract)
    _validate_venue_costs(venue, costs, contract)
    _validate_orderbook(orderbook)
    _expect(runtime, "shadow_execution_model", "nautilus_event_v1")
    regime = _section(raw, "regime")
    regime_config = _validated_regime(regime)
    policy = _validated_regime_policy(entry, regime)
    metalabel_mode = _text(runtime, "metalabel_mode")
    if metalabel_mode not in {"off", "observe"}:
        raise ValueError("runtime.metalabel_mode must be off|observe")
    if metalabel_mode != _text(model, "mode"):
        raise ValueError("runtime.metalabel_mode must equal model.mode")
    return HypervelocityProfile(
        profile_id=_text(raw, "profile"),
        symbol=_text(raw, "symbol"),
        timeframe=_text(raw, "timeframe"),
        strategy_id=_text(raw, "strategy_id"),
        position_mode=_text(raw, "position_mode"),
        max_positions_per_symbol=_integer(raw, "max_positions_per_symbol"),
        direction_mode=_text(raw, "direction_mode"),
        allow_reversal_while_open=_boolean(raw, "allow_reversal_while_open"),
        switch_after_exit=_boolean(raw, "switch_after_exit"),
        margin_fraction=_number(allocation, "margin_fraction"),
        leverage=_number(allocation, "leverage"),
        target_margin_pct=_number(exits, "target_margin_pct"),
        open_position_range_policy=_text(exits, "open_position_range_policy"),
        margin_mode=cast(Literal["isolated"], _text(venue, "margin_mode")),
        live_canary_max_notional_usd=_positive_number(
            venue,
            "live_canary_max_notional_usd",
        ),
        size_decimals=_integer(venue, "size_decimals"),
        venue_max_leverage=_number(venue, "venue_max_leverage"),
        fee_tier=_integer(costs, "fee_tier"),
        maker_fee_rate=_number(costs, "maker_fee_rate"),
        taker_fee_rate=_number(costs, "taker_fee_rate"),
        slippage_bps=_number(costs, "slippage_bps"),
        funding_refresh_seconds=_number(costs, "funding_refresh_seconds"),
        entry_ttl_seconds=_number(execution, "entry_ttl_seconds"),
        execution_submit_latency_ms=_integer(execution, "submit_latency_ms"),
        execution_cancel_latency_ms=_integer(execution, "cancel_latency_ms"),
        execution_update_latency_ms=_integer(execution, "update_latency_ms"),
        execution_max_event_age_ms=_integer(execution, "max_event_age_ms"),
        restart_queue_policy=cast(
            Literal["requeue_behind_displayed_liquidity"],
            _text(execution, "restart_queue_policy"),
        ),
        liquidation_execution_model=cast(
            Literal["hyperliquid_market_liquidation_v2"],
            _text(execution, "liquidation_execution_model"),
        ),
        partial_liquidation_supported=_boolean(
            execution,
            "partial_liquidation_supported",
        ),
        partial_liquidation_threshold_usd=_number(
            execution,
            "partial_liquidation_threshold_usd",
        ),
        partial_liquidation_fraction=_number(
            execution,
            "partial_liquidation_fraction",
        ),
        liquidation_cooldown_ms=_integer(execution, "liquidation_cooldown_ms"),
        backstop_liquidation_supported=_boolean(
            execution,
            "backstop_liquidation_supported",
        ),
        backstop_maintenance_fraction=_number(
            execution,
            "backstop_maintenance_fraction",
        ),
        backstop_accounting_model=cast(
            Literal["isolated_margin_transfer_composite_v1"],
            _text(execution, "backstop_accounting_model"),
        ),
        expired_entry_rearm_policy=_text(execution, "expired_entry_rearm_policy"),
        same_direction_reentry_policy=_text(execution, "same_direction_reentry_policy"),
        reentry_cooldown_bars=_integer(execution, "reentry_cooldown_bars"),
        orderbook_archive_enabled=_boolean(orderbook, "archive_enabled"),
        orderbook_archive_depth_levels=_integer(orderbook, "archive_depth_levels"),
        runtime_mode=_text(runtime, "mode"),
        shadow_execution_model=cast(
            Literal["nautilus_event_v1"],
            _text(runtime, "shadow_execution_model"),
        ),
        initial_cash_usd=_positive_number(runtime, "initial_cash_usd"),
        export_path=Path(_text(runtime, "export_path")),
        lookback_days=_integer(runtime, "lookback_days"),
        strict_hl_only=_boolean(runtime, "strict_hl_only"),
        poll_interval_seconds=_number(runtime, "poll_interval_seconds"),
        metalabel_mode=metalabel_mode,
        model_long_bundle=Path(_text(model, "long_bundle")),
        model_short_bundle=Path(_text(model, "short_bundle")),
        regime_config=regime_config,
        execution_timeframe=cast(Literal["1m"], policy["execution_timeframe"]),
        primary_timeframe=cast(Literal["5m"], policy["primary_timeframe"]),
        context_timeframe=cast(Literal["15m"], policy["context_timeframe"]),
        context_is_hard_gate=cast(bool, policy["context_is_hard_gate"]),
        allowed_entry_states=cast(tuple[str, ...], policy["allowed_entry_states"]),
        blocked_entry_states=cast(tuple[str, ...], policy["blocked_entry_states"]),
        breakout_requires_direction=True,
        confidence_is_gate=cast(bool, policy["confidence_is_gate"]),
        peak_observer=peak_observer,
    )


def _validate_identity(raw: Mapping[str, object]) -> None:
    _expect(raw, "profile", "hypervelocity_faithful_v2")
    _expect(raw, "symbol", "BTC")
    _expect(raw, "timeframe", "1m")
    _expect(raw, "strategy_id", "hypervelocity_1m_scalper")
    _expect(raw, "position_mode", "one_way")
    _expect(raw, "max_positions_per_symbol", 1)
    _expect(raw, "direction_mode", "regime_bidirectional")
    _expect(raw, "allow_reversal_while_open", False)
    _expect(raw, "switch_after_exit", True)


def _validate_contract(
    allocation: Mapping[str, object],
    exits: Mapping[str, object],
    execution: Mapping[str, object],
    model: Mapping[str, object],
    contract: HypervelocityContract,
) -> None:
    _expect(allocation, "margin_fraction", contract.margin_fraction)
    _expect(allocation, "leverage", contract.leverage)
    _expect(allocation, "notional_fraction", contract.notional_fraction)
    _expect(exits, "target_margin_pct", contract.target_margin_pct)
    _expect(exits, "target_price_fraction", contract.target_price_fraction)
    _expect(exits, "open_position_range_policy", "hold_until_target")
    _expect(execution, "order_type", "limit")
    _expect(execution, "time_in_force", "post_only")
    _expect(execution, "fill_rule", "public_l2_trade_event_tape")
    _expect(execution, "fill_model", "nautilus_event_v1")
    _expect(execution, "legacy_comparator", "legacy_bar_through_v1")
    _expect(execution, "legacy_fill_rule", "through_one_tick")
    _expect(execution, "price_tick_mode", "hyperliquid_dynamic")
    _expect(execution, "paper_submit_enabled", False)
    _expect(execution, "submit_latency_ms", 50)
    _expect(execution, "cancel_latency_ms", 50)
    _expect(execution, "update_latency_ms", 50)
    _expect(execution, "max_event_age_ms", 6000)
    _expect(
        execution,
        "restart_queue_policy",
        "requeue_behind_displayed_liquidity",
    )
    _expect(
        execution,
        "liquidation_execution_model",
        "hyperliquid_market_liquidation_v2",
    )
    _expect(execution, "partial_liquidation_supported", True)
    _expect(execution, "partial_liquidation_threshold_usd", 100_000.0)
    _expect(execution, "partial_liquidation_fraction", 0.20)
    _expect(execution, "liquidation_cooldown_ms", 30_000)
    _expect(execution, "backstop_liquidation_supported", True)
    _expect(execution, "backstop_maintenance_fraction", 2.0 / 3.0)
    _expect(
        execution,
        "backstop_accounting_model",
        "isolated_margin_transfer_composite_v1",
    )
    _expect(execution, "entry_ttl_seconds", contract.entry_ttl_seconds)
    _expect(
        execution,
        "expired_entry_rearm_policy",
        contract.expired_entry_rearm_policy,
    )
    _expect(
        execution,
        "same_direction_reentry_policy",
        contract.same_direction_reentry_policy,
    )
    _expect(execution, "reentry_cooldown_bars", 1)
    _expect(model, "may_filter", False)
    _expect(model, "may_scale", False)


def _validate_venue_costs(
    venue: Mapping[str, object],
    costs: Mapping[str, object],
    contract: HypervelocityContract,
) -> None:
    _expect(venue, "name", "hyperliquid")
    _expect(venue, "network", "mainnet")
    _expect(venue, "margin_mode", contract.margin_mode)
    _positive_number(venue, "live_canary_max_notional_usd")
    _expect(venue, "instrument_spec_source", "public_meta")
    _expect(venue, "size_decimals", 5)
    _expect(venue, "venue_max_leverage", 40.0)
    venue_max = _number(venue, "venue_max_leverage")
    if contract.leverage > venue_max:
        raise ValueError("strategy leverage exceeds venue_max_leverage")
    _expect(costs, "fee_source", "hyperliquid_base_tier")
    _expect(costs, "fee_tier", 0)
    _expect(costs, "maker_fee_rate", 0.00015)
    _expect(costs, "taker_fee_rate", 0.00045)
    _expect(costs, "slippage_bps", 0.0)
    _expect(costs, "funding_source", "live_meta_and_asset_contexts")
    _expect(costs, "funding_refresh_seconds", 60.0)
    _expect(costs, "funding_accrual", "hourly_boundary")


def _validate_orderbook(orderbook: Mapping[str, object]) -> None:
    """Validate the replay archive contract used by the live backend."""
    _expect(orderbook, "archive_enabled", True)
    _expect(orderbook, "archive_depth_levels", 20)


def _validated_regime(section: Mapping[str, object]) -> RegimeClassifierConfig:
    expected = asdict(faithful_regime_config())
    inactive = {"choppiness_length", "choppiness_range_threshold"}
    parameters: dict[str, object] = {}
    for key, expected_value in expected.items():
        if key in inactive:
            parameters[key] = expected_value
            continue
        actual = section.get(key)
        if actual != expected_value:
            raise ValueError(f"regime.{key} must be {expected_value!r}, got {actual!r}")
        parameters[key] = actual
    return RegimeClassifierConfig(**cast(dict[str, object], parameters))


def _validated_regime_policy(
    entry: Mapping[str, object],
    regime: Mapping[str, object],
) -> dict[str, object]:
    _expect(
        entry,
        "allowed_states",
        ["TREND_UP", "TREND_DOWN", "BREAKOUT_DIRECTION_CONFIRMED"],
    )
    _expect(entry, "blocked_states", ["RANGE", "TRANSITION", "UNKNOWN"])
    _expect(entry, "confidence_is_gate", False)
    _expect(regime, "execution_timeframe", "1m")
    _expect(regime, "primary_timeframe", "5m")
    _expect(regime, "context_timeframe", "15m")
    _expect(regime, "context_is_hard_gate", False)
    return {
        "execution_timeframe": "1m",
        "primary_timeframe": "5m",
        "context_timeframe": "15m",
        "context_is_hard_gate": False,
        "allowed_entry_states": ("TREND_UP", "TREND_DOWN", "BREAKOUT"),
        "blocked_entry_states": ("RANGE", "TRANSITION", "UNKNOWN"),
        "confidence_is_gate": False,
    }


def _validated_peak_observer(section: Mapping[str, object]) -> PeakObserverConfig:
    """Return the frozen report-only peak observer configuration."""
    return PeakObserverConfig(
        mode=cast(Literal["off", "observe"], _text(section, "mode")),
        candidate_id=_text(section, "candidate_id"),
        activation_margin_pct=_number(section, "activation_margin_pct"),
        lock_ratio=_number(section, "lock_ratio"),
        minimum_stop_move_fraction=_number(
            section,
            "minimum_stop_move_fraction",
        ),
        update_cooldown_seconds=_number(section, "update_cooldown_seconds"),
        sample_interval_seconds=_number(section, "sample_interval_seconds"),
        execution_authority=cast(
            Literal["none"],
            _text(section, "execution_authority"),
        ),
    )


def _section(raw: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Hypervelocity config requires [{name}]")
    return cast(dict[str, object], value)


def _expect(section: Mapping[str, object], key: str, expected: object) -> None:
    actual = section.get(key)
    if actual != expected:
        rendered = (
            str(expected).lower() if isinstance(expected, bool) else repr(expected)
        )
        raise ValueError(f"{key} must be {rendered}, got {actual!r}")


def _text(section: Mapping[str, object], key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(section: Mapping[str, object], key: str) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _number(section: Mapping[str, object], key: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _positive_number(section: Mapping[str, object], key: str) -> float:
    value = _number(section, key)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{key} must be positive and finite")
    return value


def _boolean(section: Mapping[str, object], key: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value
