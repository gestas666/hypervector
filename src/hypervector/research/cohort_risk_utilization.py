"""Read-only evidence for effective cohort sizing and binding notional caps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

Record = Mapping[str, object]


def cohort_risk_utilization(
    records: Sequence[Record],
    *,
    run_id: str,
) -> dict[str, object]:
    """Project configured versus effective margin without changing execution."""
    identity = _latest_payload(records, run_id, "configuration_identity")
    snapshot = _latest_payload(records, run_id, "cohort_snapshot")
    account_value = _positive_number(
        snapshot.get("account_value_usd"),
        "account value",
    )
    assets = _object_list(identity.get("assets"), "configured assets")
    projections = [_asset_projection(asset, account_value) for asset in assets]
    by_asset = _indexed_assets(projections)
    by_provider, by_provider_side = _provider_projections(
        identity,
        assets,
        account_value,
    )
    execution_symbols = _execution_symbols(identity, by_asset, by_provider)
    maximum_positions = _maximum_positions(identity, len(execution_symbols))
    maximum_margin = _maximum_margin_fraction(
        by_asset,
        by_provider,
        by_provider_side,
        execution_symbols,
        maximum_positions,
    )
    return {
        "schema_version": 1,
        "mode": "cohort_runtime_risk_utilization_v1",
        "contract": _contract(),
        "account_value_usd": account_value,
        "summary": _summary(
            projections,
            execution_symbols,
            maximum_positions,
            by_provider,
            by_provider_side,
            maximum_margin,
        ),
        "by_asset": by_asset,
        "by_provider_symbol": by_provider,
        "by_provider_symbol_side": by_provider_side,
    }


def _summary(
    projections: Sequence[tuple[str, dict[str, object]]],
    execution_symbols: frozenset[str],
    maximum_positions: int,
    by_provider: Record,
    by_provider_side: Record,
    maximum_margin: float,
) -> dict[str, object]:
    return {
        "configured_assets": len(projections),
        "executable_assets": len(execution_symbols),
        "cap_bound_assets": sum(bool(row["cap_binding"]) for _, row in projections),
        "configured_maximum_positions": maximum_positions,
        "provider_symbols": len(by_provider),
        "provider_symbol_overrides": sum(
            _mapping(row, "provider sizing").get("sizing_source") == "provider_override"
            for row in by_provider.values()
        ),
        "provider_direction_overrides": len(by_provider_side),
        "maximum_simultaneous_effective_margin_fraction": maximum_margin,
    }


def _asset_projection(
    asset: Record,
    account_value: float,
) -> tuple[str, dict[str, object]]:
    symbol = _text(asset.get("symbol"), "asset symbol")
    leverage = _positive_number(asset.get("leverage"), f"{symbol} leverage")
    margin_fraction = _fraction(
        asset.get("margin_fraction"), f"{symbol} margin fraction"
    )
    cap = _positive_number(asset.get("max_notional_usd"), f"{symbol} maximum notional")
    return symbol, _sizing_projection(account_value, leverage, margin_fraction, cap)


def _sizing_projection(
    account_value: float,
    leverage: float,
    margin_fraction: float,
    cap: float,
) -> dict[str, object]:
    uncapped = account_value * margin_fraction * leverage
    planned = min(uncapped, cap)
    return {
        "configured_leverage": leverage,
        "configured_margin_fraction": margin_fraction,
        "configured_max_notional_usd": cap,
        "uncapped_notional_usd": uncapped,
        "planned_notional_usd": planned,
        "planned_margin_usd": planned / leverage,
        "effective_margin_fraction": planned / leverage / account_value,
        "notional_fraction_of_equity": planned / account_value,
        "cap_utilization_ratio": planned / uncapped,
        "cap_binding": uncapped > cap,
    }


def _provider_projections(
    identity: Record,
    assets: tuple[Record, ...],
    account_value: float,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    asset_rows = {_text(asset.get("symbol"), "asset symbol"): asset for asset in assets}
    providers = _optional_object_list(identity.get("providers"), "configured providers")
    result: dict[str, dict[str, object]] = {}
    directional: dict[str, dict[str, object]] = {}
    for provider in providers:
        strategy = _text(provider.get("strategy_id"), "provider strategy_id")
        overrides = _mapping_or_empty(provider.get("sizing_overrides"))
        direction_overrides = _mapping_or_empty(
            provider.get("directional_sizing_overrides")
        )
        for symbol in _string_list(
            provider.get("execution_symbols"), "execution symbols"
        ):
            asset = asset_rows.get(symbol)
            if asset is None:
                raise ValueError("provider sizing references an unknown asset")
            key = f"{strategy}|{symbol}"
            if key in result:
                raise ValueError(f"duplicate provider-symbol sizing: {key}")
            row = _provider_projection(asset, overrides.get(symbol), account_value)
            result[key] = row
            _append_directional_projections(
                directional,
                strategy,
                asset,
                direction_overrides.get(symbol),
                account_value,
            )
    return result, directional


def _append_directional_projections(
    result: dict[str, dict[str, object]],
    strategy: str,
    asset: Record,
    overrides: object,
    account_value: float,
) -> None:
    """Append explicit route-side policies without synthesizing fallbacks."""
    if overrides is None:
        return
    symbol = _text(asset.get("symbol"), "asset symbol")
    for raw_side, policy in _mapping(overrides, "directional sizing").items():
        side = _text(raw_side, "directional sizing side")
        if side not in {"long", "short"}:
            raise ValueError("directional sizing side must be long or short")
        key = f"{strategy}|{symbol}|{side}"
        if key in result:
            raise ValueError(f"duplicate provider-symbol-side sizing: {key}")
        row = _provider_projection(asset, policy, account_value)
        row["sizing_source"] = "provider_direction_override"
        result[key] = row


def _provider_projection(
    asset: Record,
    override: object,
    account_value: float,
) -> dict[str, object]:
    symbol = _text(asset.get("symbol"), "asset symbol")
    leverage = _positive_number(asset.get("leverage"), f"{symbol} leverage")
    policy = (
        asset if override is None else _mapping(override, "provider sizing override")
    )
    margin = _fraction(policy.get("margin_fraction"), f"{symbol} margin fraction")
    cap = _positive_number(policy.get("max_notional_usd"), f"{symbol} maximum notional")
    asset_cap = _positive_number(
        asset.get("max_notional_usd"), f"{symbol} asset ceiling"
    )
    if cap > asset_cap:
        raise ValueError("provider sizing exceeds the asset adapter ceiling")
    row = _sizing_projection(account_value, leverage, margin, cap)
    row["sizing_source"] = "asset_default" if override is None else "provider_override"
    return row


def _maximum_positions(identity: Record, executable_asset_count: int) -> int:
    policy = _mapping(identity.get("position_policy"), "position policy")
    value = policy.get("maximum_concurrent_positions")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("maximum concurrent positions must be an integer")
    if value < executable_asset_count:
        raise ValueError("maximum concurrent positions must cover executable assets")
    return value


def _execution_symbols(
    identity: Record,
    by_asset: Record,
    by_provider: Record,
) -> frozenset[str]:
    if identity.get("providers") is None:
        return frozenset(_text(symbol, "asset symbol") for symbol in by_asset)
    return frozenset(_provider_symbol(key) for key in by_provider)


def _indexed_assets(
    projections: Sequence[tuple[str, dict[str, object]]],
) -> dict[str, dict[str, object]]:
    by_asset: dict[str, dict[str, object]] = {}
    for symbol, row in projections:
        if symbol in by_asset:
            raise ValueError(f"duplicate configured asset symbol: {symbol}")
        by_asset[symbol] = row
    return by_asset


def _maximum_margin_fraction(
    by_asset: Record,
    by_provider: Record,
    by_provider_side: Record,
    execution_symbols: frozenset[str],
    maximum_positions: int,
) -> float:
    margins = {
        symbol: _positive_number(row.get("effective_margin_fraction"), symbol)
        for symbol, raw in by_asset.items()
        for row in (_mapping(raw, f"asset sizing {symbol}"),)
        if symbol in execution_symbols
    }
    for providers in (by_provider, by_provider_side):
        for key, raw in providers.items():
            row = _mapping(raw, f"provider sizing {key}")
            symbol = _provider_symbol(key)
            margin = _positive_number(row.get("effective_margin_fraction"), key)
            margins[symbol] = max(margins.get(symbol, 0.0), margin)
    return sum(sorted(margins.values(), reverse=True)[:maximum_positions])


def _provider_symbol(value: object) -> str:
    key = _text(value, "provider-symbol key")
    parts = key.split("|")
    if len(parts) not in {2, 3} or not all(part.strip() for part in parts):
        raise ValueError("provider-symbol key is invalid")
    return parts[1]


def _latest_payload(
    records: Sequence[Record],
    run_id: str,
    event_type: str,
) -> Record:
    run = _text(run_id, "run_id")
    record = next(
        (
            row
            for row in reversed(records)
            if row.get("run_id") == run and row.get("event_type") == event_type
        ),
        None,
    )
    if record is None:
        raise ValueError(f"{event_type} is required for risk utilization")
    return _mapping(record.get("payload"), f"{event_type} payload")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "automatic_sizing_change": False,
    }


def _object_list(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    return tuple(_mapping(item, label) for item in value)


def _optional_object_list(value: object, label: str) -> tuple[Record, ...]:
    if value is None:
        return ()
    return _object_list(value, label)


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return tuple(_text(item, label) for item in value)


def _mapping_or_empty(value: object) -> Record:
    return {} if value is None else _mapping(value, "provider sizing overrides")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _fraction(value: object, label: str) -> float:
    number = _positive_number(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
