"""Provider-symbol configuration compatibility for live execution evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.research.cohort_live_audit_values import (
    is_armed_live,
    mapping,
    mapping_list,
    payload,
    text,
)
from hypervector.research.cohort_trade_performance import (
    build_all_time_trade_performance,
)
from hypervector.research.cohort_repeatability_evidence import (
    build_repeatability_evidence,
)

Record = Mapping[str, object]


def build_provider_contract_history(
    cohort_records: Sequence[Record],
    current_identity: Record,
    trades: Sequence[Record],
) -> dict[str, object]:
    """Select outcomes with an unchanged provider-symbol config contract."""
    if not trades:
        return _empty_history(current_identity)
    identities = _configuration_identities(cohort_records)
    current_run = text(current_identity.get("run_id"), "current run id")
    if identities.get(current_run) is not current_identity:
        raise ValueError("current configuration identity is not in cohort evidence")
    selected: list[Record] = []
    incompatible = 0
    not_executable = 0
    unverifiable = 0
    pair_runs: dict[str, set[str]] = {}
    for trade in trades:
        outcome = _classify_trade(trade, current_identity, identities)
        if outcome == "not_currently_executable":
            not_executable += 1
        elif outcome == "unverifiable_source_contract":
            unverifiable += 1
        elif outcome == "incompatible":
            incompatible += 1
        else:
            selected.append(trade)
            pair_runs.setdefault(_trade_pair(trade), set()).add(
                text(trade.get("source_run_id"), "trade source run")
            )
    performance = _performance(selected)
    return {
        "schema_version": 1,
        "scope": "provider_execution_contract_history",
        "evidence_state": "config_contract_classified",
        "contract": _report_contract(),
        "current_run_id": current_run,
        "current_profile_fingerprint": text(
            current_identity.get("profile_fingerprint"),
            "current profile fingerprint",
        ),
        "compatible_trades": len(selected),
        "incompatible_trades": incompatible,
        "not_currently_executable_trades": not_executable,
        "unverifiable_source_contract_trades": unverifiable,
        "performance": performance,
        "repeatability": build_repeatability_evidence(selected),
        "by_provider_symbol": _pair_evidence(pair_runs, current_identity, identities),
        "limitations": _limitations(),
    }


def _empty_history(current: Record) -> dict[str, object]:
    return {
        "schema_version": 1,
        "scope": "provider_execution_contract_history",
        "evidence_state": "not_applicable_no_live_trades",
        "contract": _report_contract(),
        "current_run_id": text(current.get("run_id"), "current run id"),
        "current_profile_fingerprint": text(
            current.get("profile_fingerprint"), "current profile fingerprint"
        ),
        "compatible_trades": 0,
        "incompatible_trades": 0,
        "not_currently_executable_trades": 0,
        "unverifiable_source_contract_trades": 0,
        "performance": _performance(()),
        "repeatability": build_repeatability_evidence(()),
        "by_provider_symbol": {},
        "limitations": _limitations(),
    }


def _classify_trade(
    trade: Record,
    current: Record,
    identities: Mapping[str, Record],
) -> str:
    strategy, symbol = _trade_identity(trade)
    current_contract = _pair_contract(current, strategy, symbol)
    if current_contract is None:
        return "not_currently_executable"
    source_run = text(trade.get("source_run_id"), "trade source run")
    source = identities.get(source_run)
    if source is None:
        raise ValueError(
            f"trade source configuration identity is missing: {source_run}"
        )
    try:
        source_contract = _pair_contract(source, strategy, symbol)
    except ValueError:
        return "unverifiable_source_contract"
    if source_contract is None:
        return "incompatible"
    return (
        "compatible"
        if _fingerprint(source_contract) == _fingerprint(current_contract)
        else "incompatible"
    )


def _configuration_identities(records: Sequence[Record]) -> dict[str, Record]:
    identities: dict[str, Record] = {}
    for row in records:
        if row.get("event_type") != "configuration_identity" or not is_armed_live(row):
            continue
        if payload(row).get("symbol") != "MULTI":
            continue
        run_id = text(row.get("run_id"), "configuration run id")
        if run_id in identities:
            raise ValueError(f"duplicate cohort configuration identity for {run_id}")
        identities[run_id] = row
    if not identities:
        raise ValueError("provider contract history requires armed live identities")
    return identities


def _pair_contract(
    identity: Record,
    strategy_id: str,
    symbol: str,
) -> dict[str, object] | None:
    values = payload(identity)
    providers = mapping_list(values.get("providers"), "configuration providers")
    target = _target_provider(providers, strategy_id, symbol)
    if target is None or symbol not in _strings(
        target.get("execution_symbols"), "provider execution symbols"
    ):
        return None
    asset = _target_asset(values, symbol)
    peers = [
        _provider_projection(row, symbol) for row in providers if _serves(row, symbol)
    ]
    return {
        "target_strategy_id": strategy_id,
        "symbol": symbol,
        "asset": dict(asset),
        "providers_for_symbol": sorted(peers, key=lambda row: str(row["strategy_id"])),
        "position_policy": _optional_policy(values, "position_policy"),
        "routing_policy": _optional_policy(values, "routing_policy"),
        "runtime": _optional_policy(values, "runtime"),
    }


def _provider_projection(provider: Record, symbol: str) -> dict[str, object]:
    sides = _strings(provider.get("sides"), "provider sides")
    execution_symbols = _strings(
        provider.get("execution_symbols"), "provider execution symbols"
    )
    return {
        "strategy_id": text(provider.get("strategy_id"), "provider strategy id"),
        "sides": sides,
        "priority": provider.get("priority"),
        "position_policy": provider.get("position_policy"),
        "timeframe": provider.get("timeframe"),
        "maximum_entry_delay_seconds": provider.get("maximum_entry_delay_seconds"),
        "execution_enabled": symbol in execution_symbols,
        "execution_side_override": _symbol_value(
            provider, "execution_side_overrides", symbol
        ),
        "entry_context_override": _symbol_value(
            provider, "entry_context_overrides", symbol
        ),
        "sizing_override": _symbol_value(provider, "sizing_overrides", symbol),
        "execution": ProviderExecutionContract.from_payload(
            provider.get("execution")
        ).as_payload(),
        "source_profile": provider.get("source_profile"),
    }


def _target_provider(
    providers: Sequence[Record], strategy_id: str, symbol: str
) -> Record | None:
    matches = [
        row
        for row in providers
        if row.get("strategy_id") == strategy_id and _serves(row, symbol)
    ]
    if len(matches) > 1:
        raise ValueError(f"duplicate provider contract for {strategy_id}|{symbol}")
    return matches[0] if matches else None


def _target_asset(values: Record, symbol: str) -> Record:
    assets = mapping_list(values.get("assets"), "configuration assets")
    matches = [row for row in assets if row.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError(f"configuration requires one asset contract for {symbol}")
    return matches[0]


def _serves(provider: Record, symbol: str) -> bool:
    return symbol in _strings(provider.get("symbols"), "provider symbols")


def _symbol_value(provider: Record, field: str, symbol: str) -> object:
    raw = provider.get(field)
    if raw is None:
        return None
    return mapping(raw, f"provider {field}").get(symbol)


def _optional_policy(values: Record, field: str) -> dict[str, object] | None:
    raw = values.get(field)
    return None if raw is None else dict(mapping(raw, field))


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must be unique")
    return list(value)


def _trade_identity(trade: Record) -> tuple[str, str]:
    return (
        text(trade.get("strategy_id"), "trade strategy"),
        text(trade.get("symbol"), "trade symbol"),
    )


def _trade_pair(trade: Record) -> str:
    strategy, symbol = _trade_identity(trade)
    return f"{strategy}|{symbol}"


def _fingerprint(value: Record) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _performance(trades: Sequence[Record]) -> dict[str, object]:
    performance = build_all_time_trade_performance(trades)
    performance["scope"] = "provider_execution_contract_history"
    performance["limitations"] = _limitations()
    return performance


def _pair_evidence(
    pair_runs: Mapping[str, set[str]],
    current: Record,
    identities: Mapping[str, Record],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for pair, runs in sorted(pair_runs.items()):
        strategy, symbol = pair.split("|", maxsplit=1)
        current_contract = _pair_contract(current, strategy, symbol)
        if current_contract is None:
            raise ValueError("selected trade lacks a current executable contract")
        output[pair] = {
            "configuration_contract_sha256": _fingerprint(current_contract),
            "configuration_contract_match": True,
            "source_run_ids": sorted(runs),
            "source_profile_fingerprints": sorted(
                {
                    text(identities[run].get("profile_fingerprint"), "source profile")
                    for run in runs
                }
            ),
            "implementation_identity": _implementation_identity(
                runs, current, identities
            ),
        }
    return output


def _implementation_identity(
    runs: set[str], current: Record, identities: Mapping[str, Record]
) -> dict[str, object]:
    current_hash = _implementation_sha(current)
    hashes_by_run = {run: _implementation_sha(identities[run]) for run in runs}
    source_hashes = sorted({value for value in hashes_by_run.values() if value})
    missing = sorted(run for run, value in hashes_by_run.items() if value is None)
    established = (
        not missing and current_hash is not None and source_hashes == [current_hash]
    )
    return {
        "current_sha256": current_hash,
        "source_sha256s": source_hashes,
        "missing_source_run_ids": missing,
        "equivalence_established": established,
    }


def _implementation_sha(identity: Record) -> str | None:
    backup = payload(identity).get("prestart_backup")
    if backup is None:
        return None
    value = mapping(backup, "prestart backup").get("implementation_sha256")
    if value is None:
        return None
    return text(value, "implementation sha256")


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "compatibility covers symbol-local configuration and shared routing policy",
        "implementation equivalence is reported separately and may be unestablished",
        "legacy source contracts that cannot be reconstructed are counted as unverifiable",
        "matched trades remain a small descriptive sample rather than proof of edge",
        "this report cannot filter, size, route, close, or submit a trade",
    ]
