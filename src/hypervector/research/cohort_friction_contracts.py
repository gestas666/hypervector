"""Typed research and runtime contracts for cohort friction comparison."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.research.cohort_friction_contract_models import (
    ModeledExecutionContract,
)

Record = Mapping[str, object]

# Research-modeled mechanics keyed by (strategy_id, symbol), with a
# (strategy_id, None) entry as the provider-wide fallback. Empty until a
# profile's research is reviewed; unlisted routes report as unmodeled.
_MODELED: dict[tuple[str, str | None], ModeledExecutionContract] = {}


def modeled_contract(
    strategy: str,
    symbol: str | None = None,
) -> ModeledExecutionContract | None:
    """Resolve cited mechanics for an exact pair before provider fallback."""
    return _MODELED.get((strategy, symbol)) or _MODELED.get((strategy, None))


def symbol_override_modeled_contract(
    strategy: str,
    symbol: str,
) -> ModeledExecutionContract | None:
    """Return cited mechanics for an explicit deployed symbol override."""
    return _MODELED.get((strategy, symbol))


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


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
