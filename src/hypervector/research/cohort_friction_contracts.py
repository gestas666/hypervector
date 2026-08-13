"""Typed research and runtime contracts for cohort friction comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import math

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.research.eth_pullback_replay import ETH_PULLBACK_STRATEGY
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.market_cipher_strategy_research import (
    resolve_market_cipher_replay_config,
)
from hypervector.research.range_onset_event_models import EventReplayConfig
from hypervector.research.source_follow_live_shape_models import SourceLiveShapeConfig

Record = Mapping[str, object]
HULK_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
HULK_ROBUST_SHORT_STRATEGY = "hulk_expansion_short_robust_v3"
RANGE_STRATEGY = "range_onset_bidirectional_v1"
LIQUIDITY_SWEEP_TARGET60_STRATEGY = "liquidity_sweep_long_1h_stop60_target60_v2"
SOURCE_STRATEGY = "hypervelocity_source_follow_bidirectional_5m_v1"
HYPE_STRATEGY = "hype_breakout_onset_bidirectional_v1"
HYPE_COMPRESSION_STRATEGY = "hype_breakout_compression_pullback_bidirectional_v1"
HIP3_SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
HIP3_BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
HIP3_BREAKOUT_FRESH15_INDEX = (
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
)
HIP3_SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
HIP3_BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"
HIP3_V25_LIFECYCLE_EVIDENCE = (
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.json"
)
V51_GROWTH_STRESS_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json"
)


@dataclass(frozen=True)
class ModeledExecutionContract:
    """Research mechanics cited for one live provider identity."""

    entry_liquidity: str
    entry_fee_bps: float
    entry_slippage_bps: float | None
    stop_policy: str
    stop_bps: float | None
    minimum_stop_bps: float | None
    maximum_stop_bps: float | None
    maximum_hold_seconds: int | None
    maximum_hold_policy: str
    hard_maximum_hold_seconds: int | None
    target_policy: str
    target_liquidity: str | None
    target_bps: float | None
    target_r_multiple: float | None
    evidence_source: str

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe modeled contract projection."""
        return asdict(self)


def modeled_contract(
    strategy: str,
    symbol: str | None = None,
) -> ModeledExecutionContract | None:
    """Resolve cited mechanics for an exact pair before provider fallback."""
    exact = _hip3_modeled_contracts().get((strategy, symbol))
    return exact or _modeled_contracts().get(strategy)


def symbol_override_modeled_contract(
    strategy: str,
    symbol: str,
) -> ModeledExecutionContract | None:
    """Return cited mechanics for an explicit deployed symbol override."""
    if (strategy, symbol) != (RANGE_STRATEGY, "SOL"):
        return None
    return replace(
        _range_modeled_contract(),
        stop_bps=80.0,
        evidence_source=V51_GROWTH_STRESS_EVIDENCE,
    )


def runtime_contract(
    provider: Record,
    asset: Record,
) -> tuple[dict[str, object] | None, str]:
    """Resolve provider mechanics, retaining legacy asset fallback support."""
    execution = provider.get("execution")
    if execution is not None:
        contract = ProviderExecutionContract.from_payload(execution)
        contract, source = _apply_symbol_stop_override(contract, provider, asset)
        return _provider_runtime_contract(contract), source
    return _asset_runtime_contract(asset), "asset_fallback"


def _apply_symbol_stop_override(
    contract: ProviderExecutionContract,
    provider: Record,
    asset: Record,
) -> tuple[ProviderExecutionContract, str]:
    """Apply the same exact symbol stop precedence as the live runner."""
    overrides = provider.get("stop_bps_overrides", {})
    if not isinstance(overrides, Mapping):
        raise ValueError("provider stop_bps_overrides must be an object")
    symbol = _nonempty_text(asset.get("symbol"), "asset symbol")
    if symbol not in overrides:
        return contract, "provider_execution"
    payload = contract.as_payload()
    payload["stop_bps"] = overrides[symbol]
    return (
        ProviderExecutionContract.from_payload(payload),
        "provider_execution_symbol_override",
    )


def contract_mismatches(
    modeled: ModeledExecutionContract,
    runtime: Record,
) -> list[str]:
    """Return exact shape fields where modeled and runtime mechanics differ."""
    mismatches: list[str] = []
    if modeled.entry_liquidity != runtime["entry_liquidity"]:
        mismatches.append("entry_liquidity")
    _compare_stop(modeled, runtime, mismatches)
    _compare_hold(modeled, runtime, mismatches)
    _compare_target(modeled, runtime, mismatches)
    return mismatches


def _modeled_contracts() -> dict[str, ModeledExecutionContract]:
    return {
        HULK_STRATEGY: _hulk_modeled_contract(),
        HULK_ROBUST_SHORT_STRATEGY: _hulk_modeled_contract(),
        RANGE_STRATEGY: _range_modeled_contract(),
        LIQUIDITY_SWEEP_TARGET60_STRATEGY: _liquidity_sweep_target60_contract(),
        SOURCE_STRATEGY: _source_modeled_contract(),
        HYPE_STRATEGY: _hype_modeled_contract(),
        HYPE_COMPRESSION_STRATEGY: _hype_modeled_contract(),
        ETH_PULLBACK_STRATEGY: _eth_pullback_modeled_contract(),
    }


def _hip3_modeled_contracts() -> dict[tuple[str, str | None], ModeledExecutionContract]:
    costs = {
        "xyz:SP500": (0.864, 1.4030892763),
        "xyz:SPCX": (0.864, 2.7515676541),
        "xyz:SNDK": (0.864, 9.2638468063),
        "xyz:GOLD": (8.64, 1.1245748882),
        "xyz:BRENTOIL": (0.864, 2.9133263178),
    }
    groups = {
        HIP3_SWING_INDEX: ("xyz:SP500", "xyz:SPCX"),
        HIP3_BREAKOUT_INDEX: ("xyz:SP500", "xyz:SPCX"),
        HIP3_BREAKOUT_FRESH15_INDEX: ("xyz:SP500", "xyz:SPCX"),
        HIP3_SWING_COMMODITY: ("xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"),
        HIP3_BREAKOUT_COMMODITY: ("xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"),
    }
    return {
        (strategy, symbol): _hip3_modeled_contract(
            costs[symbol],
            V51_GROWTH_STRESS_EVIDENCE
            if strategy == HIP3_BREAKOUT_FRESH15_INDEX
            else HIP3_V25_LIFECYCLE_EVIDENCE,
        )
        for strategy, symbols in groups.items()
        for symbol in symbols
    }


def _hip3_modeled_contract(
    costs: tuple[float, float],
    evidence_source: str,
) -> ModeledExecutionContract:
    fee_bps, slippage_bps = costs
    return ModeledExecutionContract(
        "taker",
        fee_bps,
        slippage_bps,
        "fixed_bps",
        80.0,
        None,
        None,
        86_400,
        "fixed",
        None,
        "none",
        None,
        None,
        None,
        evidence_source,
    )


def _hulk_modeled_contract() -> ModeledExecutionContract:
    hulk = resolve_market_cipher_replay_config("nominal", bar_minutes=30)
    return ModeledExecutionContract(
        "taker",
        _rate_bps(hulk.entry_fee_rate),
        hulk.entry_slippage_bps,
        "structural_clamped_bps",
        None,
        hulk.minimum_stop_bps,
        hulk.maximum_stop_bps,
        hulk.maximum_hold_bars * 30 * 60,
        "fixed",
        None,
        "reward_risk",
        "maker",
        None,
        hulk.target_r_multiple,
        "docs/reviews/2026-08-01-market-cipher-strategy-rehabilitation.md",
    )


def _range_modeled_contract() -> ModeledExecutionContract:
    range_onset = EventReplayConfig()
    return ModeledExecutionContract(
        "taker",
        _rate_bps(range_onset.taker_fee_rate),
        None,
        "fixed_bps",
        range_onset.stop_bps,
        None,
        None,
        range_onset.max_hold_ms // 1_000,
        "fixed",
        None,
        "none",
        None,
        None,
        None,
        "docs/reviews/2026-07-31-sol-range-onset-clean-extension.md",
    )


def _liquidity_sweep_target60_contract() -> ModeledExecutionContract:
    return ModeledExecutionContract(
        "taker",
        4.5,
        2.0,
        "fixed_bps",
        60.0,
        None,
        None,
        86_400,
        "fixed",
        None,
        "fixed_bps",
        "maker",
        60.0,
        None,
        "data/logs/research/bidirectional_cohort/"
        "btc_liquidity_sweep_taker_parity_20260811_v2.json",
    )


def _source_modeled_contract() -> ModeledExecutionContract:
    source = SourceLiveShapeConfig()
    return ModeledExecutionContract(
        "taker",
        _rate_bps(source.entry_fee_rate),
        source.entry_slippage_bps,
        "fixed_bps",
        source.stop_bps,
        None,
        None,
        source.maximum_hold_minutes * 60,
        "fixed",
        None,
        "fixed_bps",
        "maker",
        source.target_bps,
        None,
        "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json",
    )


def _hype_modeled_contract() -> ModeledExecutionContract:
    hype = HypeExitReplayConfig(
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )
    hard_hold_minutes = hype.hard_maximum_hold_minutes
    if hard_hold_minutes is None:
        raise RuntimeError("HYPE live-extension research requires a hard hold")
    return ModeledExecutionContract(
        "taker",
        hype.fee_bps_per_side,
        hype.slippage_bps_per_side,
        "fixed_bps",
        hype.stop_bps,
        None,
        None,
        hype.maximum_hold_minutes * 60,
        hype.maximum_hold_policy,
        hard_hold_minutes * 60,
        "none",
        None,
        None,
        None,
        "data/logs/research/hype_breakout_live_extension_parity_20260804.json",
    )


def _eth_pullback_modeled_contract() -> ModeledExecutionContract:
    eth = HypeExitReplayConfig(
        stop_bps=60.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )
    return ModeledExecutionContract(
        "taker",
        eth.fee_bps_per_side,
        eth.slippage_bps_per_side,
        "fixed_bps",
        eth.stop_bps,
        None,
        None,
        eth.maximum_hold_minutes * 60,
        "fixed",
        None,
        "none",
        None,
        None,
        None,
        "data/logs/research/eth_sol_shared_canary_falsification_20260807_v1.json",
    )


def _provider_runtime_contract(
    contract: ProviderExecutionContract,
) -> dict[str, object]:
    target_liquidity = "maker" if contract.target_policy != "none" else None
    return {
        "entry_liquidity": (
            "taker" if contract.entry_liquidity == "taker_ioc" else "maker"
        ),
        "entry_order": (
            "market_ioc"
            if contract.entry_liquidity == "taker_ioc"
            else "post_only_limit"
        ),
        "stop_policy": contract.stop_policy,
        "stop_bps": contract.stop_bps,
        "minimum_stop_bps": contract.minimum_stop_bps,
        "maximum_stop_bps": contract.maximum_stop_bps,
        "maximum_hold_seconds": contract.maximum_hold_seconds,
        "maximum_hold_policy": contract.maximum_hold_policy,
        "hard_maximum_hold_seconds": contract.hard_maximum_hold_seconds,
        "provider_recipe_exit_policy": contract.provider_recipe_exit_policy,
        "target_policy": contract.target_policy,
        "target_liquidity": target_liquidity,
        "target_bps": contract.target_bps,
        "target_r_multiple": contract.target_r_multiple,
        "safety_stop_overlay": contract.safety_stop_overlay,
        "implementation_source": (
            "src/hypervector/live/multi_asset_directional_adapter.py"
        ),
    }


def _asset_runtime_contract(asset: Record) -> dict[str, object] | None:
    if asset.get("stop_bps") is None or asset.get("maximum_hold_seconds") is None:
        return None
    return {
        "entry_liquidity": "taker",
        "entry_order": "market_ioc",
        "stop_policy": "fixed_bps",
        "stop_bps": _positive_number(asset.get("stop_bps"), "asset stop_bps"),
        "minimum_stop_bps": None,
        "maximum_stop_bps": None,
        "maximum_hold_seconds": _positive_integer(
            asset.get("maximum_hold_seconds"), "asset maximum_hold_seconds"
        ),
        "maximum_hold_policy": "fixed",
        "hard_maximum_hold_seconds": None,
        "provider_recipe_exit_policy": "ignore",
        "target_policy": "none",
        "target_liquidity": None,
        "target_bps": None,
        "target_r_multiple": None,
        "safety_stop_overlay": False,
        "implementation_source": (
            "src/hypervector/live/multi_asset_directional_adapter.py"
        ),
    }


def _compare_stop(
    modeled: ModeledExecutionContract,
    runtime: Record,
    mismatches: list[str],
) -> None:
    if modeled.stop_policy != runtime["stop_policy"]:
        mismatches.append("stop_policy")
        return
    if modeled.stop_policy == "fixed_bps":
        _append_if_different(
            modeled.stop_bps, runtime["stop_bps"], "stop_bps", mismatches
        )
    elif modeled.stop_policy == "structural_clamped_bps":
        different = not _optional_close(
            modeled.minimum_stop_bps, runtime["minimum_stop_bps"]
        ) or not _optional_close(modeled.maximum_stop_bps, runtime["maximum_stop_bps"])
        if different:
            mismatches.append("stop_bounds")


def _compare_hold(
    modeled: ModeledExecutionContract,
    runtime: Record,
    mismatches: list[str],
) -> None:
    if modeled.maximum_hold_policy != runtime["maximum_hold_policy"]:
        mismatches.append("maximum_hold_policy")
        return
    if modeled.maximum_hold_seconds != runtime["maximum_hold_seconds"]:
        mismatches.append("maximum_hold_seconds")
    if modeled.hard_maximum_hold_seconds != runtime["hard_maximum_hold_seconds"]:
        mismatches.append("hard_maximum_hold_seconds")


def _compare_target(
    modeled: ModeledExecutionContract,
    runtime: Record,
    mismatches: list[str],
) -> None:
    if modeled.target_policy != runtime["target_policy"]:
        mismatches.append("target_policy")
        return
    if modeled.target_liquidity != runtime["target_liquidity"]:
        mismatches.append("target_liquidity")
    if modeled.target_policy == "fixed_bps":
        _append_if_different(
            modeled.target_bps, runtime["target_bps"], "target_bps", mismatches
        )
    elif modeled.target_policy == "reward_risk":
        _append_if_different(
            modeled.target_r_multiple,
            runtime["target_r_multiple"],
            "target_r_multiple",
            mismatches,
        )


def _append_if_different(
    modeled: float | None,
    runtime: object,
    label: str,
    mismatches: list[str],
) -> None:
    if not _optional_close(modeled, runtime):
        mismatches.append(label)


def _optional_close(left: float | None, right: object) -> bool:
    return (
        left is None
        and right is None
        or (
            left is not None
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
            and math.isclose(left, float(right), rel_tol=1e-9, abs_tol=1e-9)
        )
    )


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _rate_bps(rate: float) -> float:
    return round(rate * 10_000.0, 10)


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
