"""Exact authority-none reconciliation for the live V58 BRENTOIL lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isclose, isfinite

from hypervector.research.v58_live_close_ledger import (
    LiveLedgerIdentity,
    fill_events,
    fill_time,
    reconcile_live_close_ledger_epochs,
    reconcile_live_entry_ledger,
)
from hypervector.research.v58_brentoil_live_contracts import (
    require_v58_checkpoint_contract,
)
from hypervector.research.v58_brentoil_live_venue import (
    brentoil_venue_asset,
    require_brentoil_flat_venue,
    require_brentoil_open_venue,
)

Record = Mapping[str, object]

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_SYMBOL = "xyz:BRENTOIL"
_ROUTE = f"{_STRATEGY}|{_SYMBOL}"
_CONTRACT_EXIT_REASONS = frozenset(
    {
        "maximum_hold",
        "maximum_hold_seconds",
        "opposite_strategy_intent",
        "protective_stop",
    }
)
_OBSERVABLE_EXIT_REASONS = _CONTRACT_EXIT_REASONS | frozenset(
    {"operator_manual_close", "provider_exit_signal"}
)


def build_v58_brentoil_lifecycle_report(
    preregistration: Record,
    checkpoint: Record,
    venue_preflight: Record,
    ledger_rows: Sequence[Record],
    ledger_evidence: Record,
    generated_at: datetime,
) -> dict[str, object]:
    """Build one exact open or resolved lifecycle report without live authority."""
    identity = _frozen_identity(preregistration)
    exit_contract = _frozen_exit_contract(preregistration)
    _require_checkpoint(checkpoint, identity)
    venue = brentoil_venue_asset(
        venue_preflight,
        profile_id=identity["profile_id"],
        profile_fingerprint=identity["profile_fingerprint"],
    )
    evidence = _ledger_evidence(ledger_evidence)
    open_row = _matching_open(checkpoint, identity)
    close_row = _matching_close(checkpoint, identity)
    if open_row is not None and close_row is not None:
        raise ValueError("V58 BRENTOIL lifecycle is both open and closed")
    if open_row is not None:
        state, actual, cleanup = _open_report(
            open_row, checkpoint, venue, ledger_rows, identity, exit_contract
        )
    elif close_row is not None:
        state, actual, cleanup = _closed_report(
            close_row, checkpoint, venue, ledger_rows, identity
        )
    else:
        raise ValueError("V58 BRENTOIL frozen lifecycle is missing")
    return _report(identity, state, actual, cleanup, evidence, generated_at)


def _open_report(
    trade: Record,
    checkpoint: Record,
    venue: Record,
    rows: Sequence[Record],
    identity: Record,
    exit_contract: Record,
) -> tuple[str, dict[str, object], dict[str, object]]:
    _require_open_trade(trade, identity, exit_contract)
    entry = _mapping(trade.get("entry"), "entry")
    _require_open_health(checkpoint, identity, entry.get("size"))
    require_brentoil_open_venue(
        venue,
        entry_size=entry.get("size"),
        protective_stop_oid=identity["protective_stop_oid"],
    )
    ledger = reconcile_live_entry_ledger(
        rows,
        trade,
        run_id=_text(identity.get("source_run_id"), "source run id"),
        profile_id=_text(identity.get("asset_profile_id"), "asset profile id"),
        profile_fingerprint=_sha256(
            identity.get("asset_profile_fingerprint"), "asset fingerprint"
        ),
        symbol=_SYMBOL,
        side="long",
    )
    marked = _mapping(trade.get("marked_economics"), "marked economics")
    actual = {
        "actual_entry_fill_claimed": True,
        "actual_exit_fill_claimed": False,
        "entry_oid": ledger.entry_oid,
        "entry_fill_count": ledger.entry_fill_count,
        "entry_price": _positive(entry.get("price"), "entry price"),
        "entry_size": _positive(entry.get("size"), "entry size"),
        "entry_time_ms": _positive_int(entry.get("venue_timestamp_ms"), "entry time"),
        "entry_fee_usd": ledger.entry_fee_usd,
        "funding_usd": _number(marked.get("funding_usd"), "open funding"),
        "marked_net_pnl_usd": _number(
            marked.get("active_lifecycle_marked_net_pnl_usd"), "marked net"
        ),
        "protective_stop_oid": identity["protective_stop_oid"],
        "protective_stop_trigger_price": exit_contract["protective_stop_trigger_price"],
    }
    return "open_protected", actual, {"venue_protected": True}


def _closed_report(
    close: Record,
    checkpoint: Record,
    venue: Record,
    rows: Sequence[Record],
    identity: Record,
) -> tuple[str, dict[str, object], dict[str, object]]:
    _require_close_identity(close, identity)
    _require_flat_health(checkpoint)
    cleanup = require_brentoil_flat_venue(venue)
    cash_close = _close_with_derived_gross(close)
    ledger = reconcile_live_close_ledger_epochs(
        rows,
        cash_close,
        identities=_ledger_identities(identity, rows, cash_close),
        symbol=_SYMBOL,
        side="long",
    )
    _require_close_cash(cash_close)
    exit_leg = _mapping(cash_close.get("exit"), "exit")
    reason = _text(cash_close.get("exit_reason"), "exit reason")
    actual = {
        "actual_entry_fill_claimed": True,
        "actual_exit_fill_claimed": True,
        "entry_oid": ledger.entry_oid,
        "exit_oid": ledger.exit_oid,
        "exit_fill_count": len(fill_events(ledger.rows, ledger.exit_oid)),
        "exit_fill_time_ms": fill_time(fill_events(ledger.rows, ledger.exit_oid)),
        "exit_price": _positive(exit_leg.get("price"), "exit price"),
        "exit_slippage_bps": _number(
            exit_leg.get("slippage_bps", 0.0), "exit slippage"
        ),
        "exit_reason": reason,
        "exit_contract_compliant": reason in _CONTRACT_EXIT_REASONS,
        "holding_time_ms": _positive_int(
            cash_close.get("holding_time_ms"), "holding time"
        ),
        "gross_market_pnl_usd": _number(
            cash_close.get("gross_market_pnl_usd"), "gross PnL"
        ),
        "fees_usd": _nonnegative(cash_close.get("fees_usd"), "fees"),
        "funding_usd": _number(cash_close.get("funding_usd"), "funding"),
        "net_pnl_usd": _number(cash_close.get("net_pnl_usd"), "net PnL"),
    }
    return "resolved", actual, cleanup


def _close_with_derived_gross(close: Record) -> Record:
    if "gross_market_pnl_usd" in close:
        return close
    entry = _mapping(close.get("entry"), "entry")
    exit_leg = _mapping(close.get("exit"), "exit")
    size = _positive(entry.get("size"), "entry size")
    gross = (
        _positive(exit_leg.get("price"), "exit price")
        - _positive(entry.get("price"), "entry price")
    ) * size
    output = dict(close)
    output["gross_market_pnl_usd"] = gross
    return output


def _frozen_identity(preregistration: Record) -> dict[str, object]:
    _require_report_only(_mapping(preregistration.get("contract"), "contract"))
    identity = dict(_mapping(preregistration.get("frozen_identity"), "identity"))
    expected = {
        "profile_id": _PROFILE,
        "strategy_id": _STRATEGY,
        "route": _ROUTE,
        "symbol": _SYMBOL,
        "side": "long",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL frozen identity differs")
    _sha256(identity.get("profile_fingerprint"), "profile fingerprint")
    runtime_run = _text(identity.get("run_id"), "run id")
    identity["source_run_id"] = _text(
        identity.get("source_run_id", runtime_run), "source run id"
    )
    _text(identity.get("asset_profile_id"), "asset profile id")
    _sha256(identity.get("asset_profile_fingerprint"), "asset fingerprint")
    identity["runtime_asset_profile_id"] = _text(
        identity.get("runtime_asset_profile_id", identity["asset_profile_id"]),
        "runtime asset profile id",
    )
    identity["runtime_asset_profile_fingerprint"] = _sha256(
        identity.get(
            "runtime_asset_profile_fingerprint",
            identity["asset_profile_fingerprint"],
        ),
        "runtime asset fingerprint",
    )
    entry_oid = _lifecycle_oid(identity.get("lifecycle_id"))
    if identity.get("entry_oid") != entry_oid:
        raise ValueError("V58 BRENTOIL entry order identity differs")
    _positive_int(identity.get("protective_stop_oid"), "protective stop oid")
    return identity


def _frozen_exit_contract(preregistration: Record) -> Record:
    contract = _mapping(preregistration.get("frozen_exit_contract"), "exit contract")
    expected = {
        "maximum_hold_seconds": 86400,
        "profit_lock_policy": "none",
        "provider_recipe_exit_policy": "ignore",
        "opposite_intent_exit_scope": (
            "selected_opposite_from_any_executable_provider_same_symbol"
        ),
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL frozen exit contract differs")
    _positive(contract.get("protective_stop_trigger_price"), "stop price")
    return contract


def _require_checkpoint(checkpoint: Record, identity: Record) -> None:
    require_v58_checkpoint_contract(
        _mapping(checkpoint.get("checkpoint_contract"), "checkpoint")
    )
    generation = _mapping(checkpoint.get("configuration_generation"), "generation")
    if generation.get("matches_runtime") is not True:
        raise ValueError("V58 BRENTOIL checkpoint configuration differs")
    lifecycle = _mapping(checkpoint.get("lifecycle"), "lifecycle")
    if (
        lifecycle.get("state") != "running_consistent"
        or lifecycle.get("faulted_assets") != []
    ):
        raise ValueError("V58 BRENTOIL checkpoint is not healthy")
    run = _mapping(_mapping(checkpoint.get("audit"), "audit").get("run"), "run")
    expected = {
        "profile_id": identity["profile_id"],
        "profile_fingerprint": identity["profile_fingerprint"],
        "run_id": identity["run_id"],
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL checkpoint run identity differs")


def _matching_open(checkpoint: Record, identity: Record) -> Record | None:
    audit = _mapping(checkpoint.get("audit"), "audit")
    open_rows = _records(
        _mapping(audit.get("open_trade_reflections"), "open trades").get("trades"),
        "open trades",
    )
    return _one_matching(open_rows, identity, "open")


def _matching_close(checkpoint: Record, identity: Record) -> Record | None:
    audit = _mapping(checkpoint.get("audit"), "audit")
    closed = _records(
        _mapping(audit.get("trade_reflections"), "closed trades").get("trades"),
        "closed trades",
    )
    return _one_matching(closed, identity, "closed")


def _one_matching(
    rows: Sequence[Record], identity: Record, label: str
) -> Record | None:
    matches = [
        row for row in rows if row.get("lifecycle_id") == identity["lifecycle_id"]
    ]
    if len(matches) > 1:
        raise ValueError(f"V58 BRENTOIL has duplicate {label} lifecycle rows")
    return matches[0] if matches else None


def _require_open_trade(trade: Record, identity: Record, exit_contract: Record) -> None:
    _require_trade_identity(trade, identity)
    stop = _mapping(trade.get("protective_stop"), "protective stop")
    stop_matches = stop.get("oid") == identity["protective_stop_oid"] and _same_number(
        stop.get("trigger_price"), exit_contract["protective_stop_trigger_price"]
    )
    if not stop_matches:
        raise ValueError("V58 BRENTOIL protective stop identity differs")
    if trade.get("target_order") is not None:
        raise ValueError("V58 BRENTOIL frozen lifecycle unexpectedly has a target")
    plan = _mapping(trade.get("exit_plan"), "exit plan")
    for key, expected in exit_contract.items():
        if key != "protective_stop_trigger_price" and plan.get(key) != expected:
            raise ValueError("V58 BRENTOIL live exit plan differs")


def _require_close_identity(close: Record, identity: Record) -> None:
    _require_trade_identity(close, identity)
    reason = _text(close.get("exit_reason"), "exit reason")
    if reason not in _OBSERVABLE_EXIT_REASONS:
        raise ValueError("V58 BRENTOIL exit reason is unrecognized")
    stop = _mapping(close.get("protective_stop"), "protective stop")
    if stop.get("oid") != identity["protective_stop_oid"]:
        raise ValueError("V58 BRENTOIL protective stop identity differs")


def _require_trade_identity(trade: Record, identity: Record) -> None:
    expected = {
        "lifecycle_id": identity["lifecycle_id"],
        "source_run_id": identity["source_run_id"],
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
        "side": "long",
    }
    if any(trade.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL lifecycle identity differs")
    profile = trade.get("source_profile_fingerprint")
    if profile is not None and profile != identity["profile_fingerprint"]:
        raise ValueError("V58 BRENTOIL lifecycle profile fingerprint differs")


def _ledger_identities(
    identity: Record, rows: Sequence[Record], close: Record
) -> tuple[LiveLedgerIdentity, ...]:
    source = LiveLedgerIdentity(
        _text(identity.get("source_run_id"), "source run id"),
        _text(identity.get("asset_profile_id"), "asset profile id"),
        _sha256(identity.get("asset_profile_fingerprint"), "asset fingerprint"),
    )
    runtime = LiveLedgerIdentity(
        _text(identity.get("run_id"), "runtime run id"),
        _text(identity.get("runtime_asset_profile_id"), "runtime asset profile id"),
        _sha256(
            identity.get("runtime_asset_profile_fingerprint"),
            "runtime asset fingerprint",
        ),
    )
    by_run = {item.run_id: item for item in (source, runtime)}
    for adopted in _adopted_ledger_identities(rows, identity, close):
        prior = by_run.get(adopted.run_id)
        if prior is not None and prior != adopted:
            raise ValueError("V58 BRENTOIL adopted run identity conflicts")
        by_run[adopted.run_id] = adopted
    return tuple(by_run[run_id] for run_id in sorted(by_run))


def _adopted_ledger_identities(
    rows: Sequence[Record], identity: Record, close: Record
) -> tuple[LiveLedgerIdentity, ...]:
    allowed_profiles = {
        (identity["asset_profile_id"], identity["asset_profile_fingerprint"]),
        (
            identity["runtime_asset_profile_id"],
            identity["runtime_asset_profile_fingerprint"],
        ),
    }
    entry = _mapping(close.get("entry"), "entry")
    size = _positive(entry.get("size"), "entry size")
    configurations = {
        _row_ledger_identity(row)
        for row in rows
        if _is_adopted_configuration(row, allowed_profiles)
    }
    adopted = {
        _row_ledger_identity(row)
        for row in rows
        if _is_adopted_open(row, allowed_profiles, identity, size)
    }
    if not adopted.issubset(configurations):
        raise ValueError("V58 BRENTOIL adopted run lacks configuration identity")
    return tuple(sorted(adopted, key=lambda item: item.run_id))


def _is_adopted_configuration(
    row: Record, allowed_profiles: set[tuple[object, object]]
) -> bool:
    if row.get("event_type") != "configuration_identity":
        return False
    if not _is_authenticated_live_row(row, allowed_profiles):
        return False
    values = _mapping(row.get("payload"), "configuration identity")
    return (
        values.get("symbol") == _SYMBOL
        and values.get("strategy_name") == "multi_strategy_bidirectional_router"
    )


def _is_adopted_open(
    row: Record,
    allowed_profiles: set[tuple[object, object]],
    identity: Record,
    size: float,
) -> bool:
    if row.get("event_type") != "state_transition":
        return False
    if not _is_authenticated_live_row(row, allowed_profiles):
        return False
    values = _mapping(row.get("payload"), "state transition")
    if (
        values.get("state") != "OPEN"
        or values.get("entry_oid") != identity["entry_oid"]
    ):
        return False
    plan = _mapping(values.get("execution_plan"), "execution plan")
    return (
        values.get("stop_oid") == identity["protective_stop_oid"]
        and values.get("target_oid") is None
        and values.get("close_oid") is None
        and plan.get("strategy_id") == _STRATEGY
        and _same_number(values.get("position_size_signed"), size)
    )


def _is_authenticated_live_row(
    row: Record, allowed_profiles: set[tuple[object, object]]
) -> bool:
    return (
        row.get("live_armed") is True
        and row.get("execution_authority") == "hyperliquid_mainnet"
        and (row.get("profile_id"), row.get("profile_fingerprint")) in allowed_profiles
    )


def _row_ledger_identity(row: Record) -> LiveLedgerIdentity:
    return LiveLedgerIdentity(
        _text(row.get("run_id"), "adopted run id"),
        _text(row.get("profile_id"), "adopted profile id"),
        _sha256(row.get("profile_fingerprint"), "adopted profile fingerprint"),
    )


def _require_open_health(
    checkpoint: Record, identity: Record, entry_size: object
) -> None:
    health = _asset_health(checkpoint)
    expected = {
        "final_state": "OPEN",
        "faults": 0,
        "protected_if_open": True,
        "stop_oid": identity["protective_stop_oid"],
    }
    if any(health.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL backend protection differs")
    orders = health.get("open_order_ids")
    if orders is not None and orders != [identity["protective_stop_oid"]]:
        raise ValueError("V58 BRENTOIL backend protection differs")
    size = health.get("position_size_signed")
    if size is None:
        position = _execution_position(checkpoint)
        if position is None:
            raise ValueError("V58 BRENTOIL backend position is missing")
        size = position.get("size_signed")
    if not _same_number(size, entry_size):
        raise ValueError("V58 BRENTOIL backend position size differs")


def _require_flat_health(checkpoint: Record) -> None:
    health = _asset_health(checkpoint)
    expected = {
        "final_state": "FLAT",
        "faults": 0,
        "stop_oid": None,
    }
    if any(health.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL backend cleanup differs")
    if health.get("open_order_ids") not in (None, []):
        raise ValueError("V58 BRENTOIL backend cleanup differs")
    if health.get("position_size_signed") not in (None, 0, 0.0):
        raise ValueError("V58 BRENTOIL backend cleanup differs")
    if _execution_position(checkpoint) is not None:
        raise ValueError("V58 BRENTOIL backend cleanup differs")


def _asset_health(checkpoint: Record) -> Record:
    audit = _mapping(checkpoint.get("audit"), "audit")
    health = _mapping(_mapping(audit.get("health"), "health").get("assets"), "assets")
    return _mapping(health.get(_SYMBOL), "BRENTOIL health")


def _execution_position(checkpoint: Record) -> Record | None:
    audit = _mapping(checkpoint.get("audit"), "audit")
    value = audit.get("execution")
    if value is None:
        return None
    execution = _mapping(value, "execution")
    matches = [
        row
        for row in _records(execution.get("open_positions", []), "open positions")
        if row.get("symbol") == _SYMBOL
    ]
    if len(matches) > 1:
        raise ValueError("V58 BRENTOIL backend positions are duplicated")
    return matches[0] if matches else None


def _require_close_cash(close: Record) -> None:
    entry = _mapping(close.get("entry"), "entry")
    exit_leg = _mapping(close.get("exit"), "exit")
    size = _positive(entry.get("size"), "entry size")
    if not _same_number(exit_leg.get("size"), size):
        raise ValueError("V58 BRENTOIL close size differs")
    gross = (
        _positive(exit_leg.get("price"), "exit price")
        - _positive(entry.get("price"), "entry price")
    ) * size
    if not isclose(
        gross, _number(close.get("gross_market_pnl_usd"), "gross PnL"), abs_tol=1e-8
    ):
        raise ValueError("V58 BRENTOIL gross cash accounting differs")
    net = (
        gross
        - _nonnegative(close.get("fees_usd"), "fees")
        + _number(close.get("funding_usd"), "funding")
    )
    if not isclose(net, _number(close.get("net_pnl_usd"), "net PnL"), abs_tol=1e-8):
        raise ValueError("V58 BRENTOIL net cash accounting differs")


def _ledger_evidence(evidence: Record) -> dict[str, object]:
    output = dict(evidence)
    _text(output.get("path"), "ledger path")
    _positive_int(output.get("bytes"), "ledger bytes")
    _sha256(output.get("sha256"), "ledger sha256")
    _positive_int(output.get("rows"), "ledger rows")
    if output.get("frozen_prefix_verified") is not True:
        raise ValueError("V58 BRENTOIL frozen ledger prefix is unverified")
    return output


def _report(
    identity: Record,
    state: str,
    actual: Record,
    cleanup: Record,
    evidence: Record,
    generated_at: datetime,
) -> dict[str, object]:
    timestamp = _aware_utc(generated_at).isoformat()
    resolved = int(state == "resolved")
    return {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_reconciliation_v1",
        "generated_at_utc": timestamp,
        "state": state,
        "identity": dict(identity),
        "summary": {"open": 1 - resolved, "resolved": resolved},
        "actual_live_lifecycle": dict(actual),
        "cleanup": dict(cleanup),
        "source_evidence": {"asset_ledger": dict(evidence)},
        "strategy_change_supported": False,
        "contract": _output_contract(),
    }


def _require_report_only(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL authority contract differs")


def _output_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": True,
    }


def _lifecycle_oid(value: object) -> int:
    lifecycle = _text(value, "lifecycle id")
    prefix, separator, suffix = lifecycle.rpartition(":")
    if prefix != _SYMBOL or separator != ":" or not suffix.isdigit():
        raise ValueError("V58 BRENTOIL lifecycle id differs")
    return int(suffix)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("V58 BRENTOIL generation time must be timezone-aware")
    return value.astimezone(UTC)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 BRENTOIL {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 BRENTOIL {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 BRENTOIL {label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"V58 BRENTOIL {label} must be lowercase sha256")
    return text


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 BRENTOIL {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 BRENTOIL {label} must be finite")
    return output


def _positive(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"V58 BRENTOIL {label} must be positive")
    return output


def _nonnegative(value: object, label: str) -> float:
    output = _number(value, label)
    if output < 0.0:
        raise ValueError(f"V58 BRENTOIL {label} must be nonnegative")
    return output


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 BRENTOIL {label} must be a positive integer")
    return value


def _same_number(left: object, right: object) -> bool:
    return isclose(
        _number(left, "numeric identity"),
        _number(right, "numeric identity"),
        abs_tol=1e-10,
    )
