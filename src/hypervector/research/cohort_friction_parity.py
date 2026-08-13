"""Report-only comparison of cohort live mechanics with cited research contracts."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import math
from statistics import median

from hypervector.research.cohort_friction_contracts import (
    ModeledExecutionContract,
    contract_mismatches,
    modeled_contract,
    runtime_contract,
    symbol_override_modeled_contract,
)

Record = Mapping[str, object]


def build_friction_parity(
    identity: Record,
    fills: Sequence[Record],
) -> dict[str, object]:
    """Compare declared research mechanics with shared live cohort mechanics."""
    assets = _asset_contracts(identity)
    grouped = _entry_fills(fills)
    results: dict[str, dict[str, object]] = {}
    for strategy, symbol, provider in _provider_symbols(identity):
        key = f"{strategy}|{symbol}"
        results[key] = _provider_parity(
            strategy,
            provider,
            assets[symbol],
            grouped.get((strategy, symbol), ()),
        )
    states = Counter(row["parity_state"] for row in results.values())
    return {
        "contract": _report_contract(),
        "summary": {
            "provider_symbols": len(results),
            "runtime_shape_aligned": states["runtime_shape_aligned"],
            "contract_mismatch": states["contract_mismatch"],
            "unsupported_contract": states["unsupported_contract"],
            "runtime_contract_missing": states["runtime_contract_missing"],
            "provider_symbols_with_entry_fills": sum(
                row["observed_entry"]["fills"] > 0 for row in results.values()
            ),
        },
        "by_provider_symbol": results,
        "limitations": [
            "observed costs describe owned fills and do not establish strategy edge",
            "private queue rank is unobservable for modeled maker entries",
            "small fill samples do not estimate a stable latency distribution",
            (
                "provider configuration describes the current profile; historical "
                "fills can retain an earlier bound execution plan"
            ),
        ],
    }


def _provider_parity(
    strategy: str,
    provider: Record,
    asset: Record,
    fills: Sequence[Record],
) -> dict[str, object]:
    symbol = _text(asset.get("symbol"), "asset symbol")
    runtime, runtime_source = runtime_contract(provider, asset)
    modeled = (
        symbol_override_modeled_contract(strategy, symbol)
        if runtime_source == "provider_execution_symbol_override"
        else modeled_contract(strategy, symbol)
    )
    if runtime is None:
        state, mismatches = "runtime_contract_missing", ["runtime_contract_missing"]
    elif modeled is None:
        state, mismatches = "unsupported_contract", ["modeled_contract_missing"]
    else:
        mismatches = contract_mismatches(modeled, runtime)
        state = "contract_mismatch" if mismatches else "runtime_shape_aligned"
    return {
        "parity_state": state,
        "mismatches": mismatches,
        "modeled_contract": modeled.as_payload() if modeled is not None else None,
        "runtime_contract": runtime,
        "runtime_contract_source": runtime_source,
        "observed_entry": _observed_entry(fills, modeled),
        "strategy_edge_identifiable": False,
        "execution_effect": "report_only",
    }


def _observed_entry(
    fills: Sequence[Record],
    modeled: ModeledExecutionContract | None,
) -> dict[str, object]:
    fees = [_fee_rate_bps(fill) for fill in fills]
    slippage = _optional_signed_values(fills, "slippage_bps")
    latency = _optional_values(fills, "acknowledgement_latency_ms")
    fee_mean = _mean(fees)
    slippage_mean = _mean(slippage)
    return {
        "status": "observed" if fills else "not_observed",
        "fills": len(fills),
        "fee_rate_bps": _summary(fees),
        "slippage_bps": _summary(slippage),
        "acknowledgement_latency_ms": _summary(latency),
        "fee_mean_minus_modeled_bps": _difference(
            fee_mean, modeled.entry_fee_bps if modeled is not None else None
        ),
        "slippage_mean_minus_modeled_bps": _difference(
            slippage_mean,
            modeled.entry_slippage_bps if modeled is not None else None,
        ),
    }


def _entry_fills(
    fills: Sequence[Record],
) -> dict[tuple[str, str], tuple[Record, ...]]:
    grouped: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for fill in fills:
        if fill.get("operation") != "entry":
            continue
        strategy = _text(fill.get("strategy_id"), "fill strategy_id")
        symbol = _text(fill.get("symbol"), "fill symbol")
        grouped[(strategy, symbol)].append(fill)
    return {key: tuple(values) for key, values in grouped.items()}


def _asset_contracts(identity: Record) -> dict[str, Record]:
    assets = _record_list(identity.get("assets"), "identity assets")
    result = {_text(row.get("symbol"), "asset symbol"): row for row in assets}
    if not result:
        raise ValueError("friction parity requires at least one asset contract")
    return result


def _provider_symbols(
    identity: Record,
) -> tuple[tuple[str, str, Record], ...]:
    pairs: list[tuple[str, str, Record]] = []
    for provider in _record_list(identity.get("providers"), "identity providers"):
        strategy = _text(provider.get("strategy_id"), "provider strategy_id")
        symbols = _text_list(provider.get("symbols"), "provider symbols")
        pairs.extend((strategy, symbol, provider) for symbol in symbols)
    return tuple(sorted(pairs, key=lambda row: (row[0], row[1])))


def _fee_rate_bps(fill: Record) -> float:
    fee = _nonnegative_number(fill.get("fee_usd"), "fill fee_usd")
    price = _positive_number(fill.get("price"), "fill price")
    size = _positive_number(fill.get("size"), "fill size")
    return fee / (price * size) * 10_000.0


def _optional_values(records: Sequence[Record], key: str) -> list[float]:
    return [
        _nonnegative_number(value, key)
        for row in records
        if (value := row.get(key)) is not None
    ]


def _optional_signed_values(records: Sequence[Record], key: str) -> list[float]:
    return [
        _finite_number(value, key)
        for row in records
        if (value := row.get(key)) is not None
    ]


def _summary(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
        }
    return {
        "count": len(values),
        "minimum": min(values),
        "median": float(median(values)),
        "maximum": max(values),
        "mean": sum(values) / len(values),
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _difference(left: float | None, right: float | None) -> float | None:
    return left - right if left is not None and right is not None else None


def _positive_number(value: object, label: str) -> float:
    number = _nonnegative_number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return number


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _record_list(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_text(item, label) for item in value)


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
    }
