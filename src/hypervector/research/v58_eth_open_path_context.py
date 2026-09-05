"""Exact sampled excursion context for the V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    directional_return_bps,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
)
from hypervector.research.v58_eth_path_economics import sampled_eth_net_path
from hypervector.research.v58_eth_censored_context import (
    EthLifecycleScope,
    awaiting_eth_path_payload,
    censored_eth_path_payload,
    select_eth_lifecycle_scope,
)
from hypervector.research.v58_eth_source_history_context import (
    load_v58_eth_source_history,
)

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"
_SYMBOL = "ETH"
_SOURCE_HISTORY = Path(
    "docs/research-journal/eth-breakout-precompression-pullback-v14.json"
)
_SOURCE_HISTORY_SHA256 = (
    "d78cc8595f2348d6ef6000f37b52a479db0a16fdd4a4f5689580adc54e1bef4f"
)


@dataclass(frozen=True)
class EthOpenPathContext:
    """Execution-incapable sampled path evidence for one ETH lifecycle."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_eth_open_path_context(
    status_path: Path,
    *,
    source_history_journal: Path | None = None,
    expected_history_journal_sha256: str | None = None,
) -> EthOpenPathContext:
    """Load one source-bound pending V58 ETH lifecycle excursion path."""
    raw = status_path.read_bytes()
    status_evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    status = _mapping(json.loads(raw), "ETH lifecycle status")
    contract, scope = _lifecycle_contract(status)
    lifecycle = scope.current
    state = scope.current_state
    ledger = _ledger_evidence(status)
    rows = _verified_rows(ledger)
    books = _eth_books(rows, contract)
    if lifecycle is None:
        payload = awaiting_eth_path_payload()
    elif state == "censored":
        payload = censored_eth_path_payload(lifecycle, contract)
    else:
        payload = _path_payload(
            status, lifecycle, contract, books, state, scope.exit_reason
        )
    history_evidence = _source_history(
        payload,
        source_history_journal,
        expected_history_journal_sha256,
        contract,
        scope.lifecycles,
    )
    if file_evidence(status_path) != status_evidence:
        raise ValueError("V58 ETH lifecycle status changed during path evaluation")
    return EthOpenPathContext(
        payload,
        {
            "status": {"path": str(status_path.resolve()), **status_evidence},
            "observer_ledger": dict(ledger),
            **history_evidence,
        },
    )


def load_v58_eth_open_path_context_with_history(
    status_path: Path,
) -> EthOpenPathContext:
    """Load the current ETH path plus the pinned compatible v14 lifecycle."""
    return load_v58_eth_open_path_context(
        status_path,
        source_history_journal=_SOURCE_HISTORY,
        expected_history_journal_sha256=_SOURCE_HISTORY_SHA256,
    )


def eth_open_path_context_payload(context: EthOpenPathContext) -> dict[str, object]:
    """Serialize sampled ETH path evidence without execution authority."""
    sampled = context.payload.get("state") in {"open", "resolved"}
    return {
        **context.payload,
        "sampled_exit_vwap_claim": sampled,
        "continuous_path_claim": False,
        "excursion_metrics_are_gross_before_costs": sampled,
        "actual_fill_claim": False,
        "strategy_change_supported": False,
        "execution_authority": context.execution_authority,
    }


def attach_eth_source_history_to_ledger(
    ledger: object, eth_path_payload: Record
) -> None:
    """Attach cumulative ETH evidence without changing watcher counters."""
    if not isinstance(ledger, list):
        raise ValueError("V58 hypothesis ledger must be an array")
    matches = [
        row
        for row in ledger
        if isinstance(row, dict) and row.get("route") == f"{_STRATEGY}|{_SYMBOL}"
    ]
    if len(matches) != 1:
        raise ValueError("V58 ETH hypothesis ledger identity is invalid")
    summary = _mapping(
        eth_path_payload.get("source_compatible_lifecycle_summary"),
        "ETH source-compatible lifecycle summary",
    )
    matches[0]["source_compatible_lifecycle_summary"] = dict(summary)


def _source_history(
    payload: dict[str, object],
    journal_path: Path | None,
    expected_sha256: str | None,
    contract: Record,
    lifecycles: Sequence[tuple[Record, str]],
) -> dict[str, object]:
    if journal_path is None and expected_sha256 is None:
        return {}
    if journal_path is None or expected_sha256 is None:
        raise ValueError("V58 ETH source history identity is incomplete")
    summary, evidence = load_v58_eth_source_history(
        journal_path,
        expected_sha256,
        current_contract=contract,
        current_lifecycles=lifecycles,
    )
    payload["source_compatible_lifecycle_summary"] = summary
    return {"source_compatible_history": evidence}


def _lifecycle_contract(
    status: Record,
) -> tuple[Record, EthLifecycleScope]:
    expected = {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH path source contract is invalid")
    contract = _mapping(status.get("contract"), "ETH lifecycle contract")
    identity = _mapping(status.get("identity"), "ETH lifecycle identity")
    _require_contract(contract, identity)
    summary = _mapping(status.get("summary"), "ETH lifecycle summary")
    attempts = _records(status.get("latest_attempts"), "ETH lifecycle attempts")
    executions = _records(status.get("latest_executions"), "ETH executions")
    scope = select_eth_lifecycle_scope(
        summary, attempts, executions, contract, status.get("state")
    )
    for lifecycle, state in scope.lifecycles:
        if state != "censored":
            status_value = "exit_pending" if state == "open" else "resolved"
            _require_lifecycle(lifecycle, contract, status=status_value)
    return contract, scope


def _require_contract(contract: Record, identity: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
        "close_on_eligible_opposite_signal": True,
        "same_cycle_reversal": False,
        "notional_usd": 750.0,
        "stop_bps": 60.0,
        "maximum_hold_minutes": 720,
        "taker_fee_rate": 0.00045,
    }
    if any(not _equal(contract.get(field), value) for field, value in expected.items()):
        raise ValueError("V58 ETH path contract is invalid")
    identity_expected = {
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": contract.get("profile_fingerprint"),
        "source_run_id": contract.get("source_run_id"),
        "compatible_run_ids": contract.get("compatible_run_ids"),
    }
    if any(identity.get(field) != value for field, value in identity_expected.items()):
        raise ValueError("V58 ETH path identity is invalid")


def _require_lifecycle(attempt: Record, contract: Record, *, status: str) -> None:
    expected = {
        "status": status,
        "strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
        "source_run_id": contract.get("source_run_id"),
    }
    if any(attempt.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH pending attempt identity is invalid")
    if attempt.get("side") not in {"long", "short"}:
        raise ValueError("V58 ETH pending attempt side is invalid")
    _positive_number(attempt.get("entry_price"), "ETH entry price")
    _positive_number(attempt.get("position_quantity"), "ETH position quantity")
    _positive_integer(attempt.get("entry_time_ms"), "ETH entry time")
    time_field = "current_exit_time_ms" if status == "exit_pending" else "exit_time_ms"
    _positive_integer(attempt.get(time_field), "ETH current exit time")
    _deadline_time(attempt, contract, resolved=status == "resolved")


def _deadline_time(attempt: Record, contract: Record, *, resolved: bool) -> int:
    deadline = attempt.get("deadline_time_ms")
    if deadline is not None or not resolved:
        return _positive_integer(deadline, "ETH deadline")
    entry_time = _positive_integer(attempt.get("entry_time_ms"), "ETH entry time")
    hold_minutes = _positive_integer(
        contract.get("maximum_hold_minutes"), "ETH maximum hold minutes"
    )
    return entry_time + hold_minutes * 60_000


def _ledger_evidence(status: Record) -> Record:
    source = _mapping(status.get("source_evidence"), "ETH source evidence")
    return _mapping(source.get("ledger"), "ETH observer ledger evidence")


def _verified_rows(ledger: Record) -> tuple[dict[str, object], ...]:
    path = Path(_text(ledger.get("path"), "ETH observer ledger path"))
    return read_jsonl_verified_prefix(
        path,
        "V58 ETH observer ledger",
        length=_positive_integer(ledger.get("stable_bytes"), "ETH ledger bytes"),
        expected_sha256=_text(ledger.get("sha256"), "ETH ledger sha256"),
    )


def _eth_books(rows: Sequence[Record], contract: Record) -> tuple[Record, ...]:
    run_ids = _text_list(contract.get("compatible_run_ids"), "compatible run ids")
    selected = tuple(row for row in rows if row.get("run_id") in run_ids)
    if not selected:
        raise ValueError("V58 ETH observer prefix lacks the compatible run")
    fingerprint = contract.get("profile_fingerprint")
    if any(row.get("profile_fingerprint") != fingerprint for row in selected):
        raise ValueError("V58 ETH compatible-run profile fingerprint is invalid")
    extracted = extract_observer_asset_books(selected, (_SYMBOL,))[_SYMBOL]
    return validated_books(extracted, symbol=_SYMBOL, run_ids=run_ids)


def _path_payload(
    status: Record,
    attempt: Record,
    contract: Record,
    books: Sequence[Record],
    state: str,
    exit_reason: str | None,
) -> dict[str, object]:
    entry_time = _positive_integer(attempt.get("entry_time_ms"), "ETH entry time")
    current_time = _positive_integer(
        _outcome(attempt, state, "exit_time_ms"), "ETH current exit time"
    )
    path = _selected_path(books, entry_time, current_time)
    returns, prices = _sampled_returns(attempt, path)
    _require_current_outcome(attempt, state, current_time, prices[-1], returns[-1])
    net_path = _sampled_net_path(status, contract, attempt, path, prices, returns)
    favorable = max(0.0, max(returns))
    adverse = max(0.0, -min(returns))
    stop_bps = _positive_number(contract.get("stop_bps"), "ETH stop bps")
    _require_stop_path_consistency(state, exit_reason, adverse, stop_bps)
    deadline = _deadline_time(attempt, contract, resolved=state == "resolved")
    gaps = _observation_gaps(entry_time, path)
    return {
        "state": state,
        "exit_reason": exit_reason,
        "route": f"{_STRATEGY}|{_SYMBOL}",
        "side": attempt["side"],
        "entry_time_ms": entry_time,
        "current_exit_time_ms": current_time,
        **_holding_payload(entry_time, current_time, deadline),
        "sampled_exit_observations": len(path),
        "current_gross_return_bps": returns[-1],
        **_economics(attempt, state, returns[-1]),
        **net_path,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "peak_giveback_bps": favorable - returns[-1],
        "stop_bps": stop_bps,
        "stop_headroom_bps": stop_bps - adverse,
        "maximum_observation_gap_ms": max(gaps),
        "p99_observation_gap_ms": _nearest_rank(gaps, 0.99),
    }


def _require_stop_path_consistency(
    state: str, exit_reason: str | None, adverse_bps: float, stop_bps: float
) -> None:
    crossed = adverse_bps >= stop_bps
    resolved_stop = state == "resolved" and exit_reason == "protective_stop"
    if crossed and not resolved_stop:
        raise ValueError("V58 ETH non-stop path crosses its protective stop")
    if resolved_stop and not crossed:
        raise ValueError("V58 ETH protective-stop path never crosses its stop")


def _sampled_net_path(
    status: Record,
    contract: Record,
    attempt: Record,
    path: Sequence[Record],
    prices: Sequence[float],
    returns: Sequence[float],
) -> dict[str, object]:
    return sampled_eth_net_path(
        status,
        contract,
        attempt,
        times_ms=tuple(book_time(row) for row in path),
        prices=prices,
        gross_returns_bps=returns,
    )


def _selected_path(
    books: Sequence[Record], entry_time: int, current_time: int
) -> list[Record]:
    path = [row for row in books if entry_time < book_time(row) <= current_time]
    if not path or book_time(path[-1]) != current_time:
        raise ValueError("V58 ETH sampled path does not reach the current exit time")
    return path


def _holding_payload(entry_time: int, current_time: int, deadline: int) -> Record:
    return {
        "deadline_time_ms": deadline,
        "holding_elapsed_seconds": (current_time - entry_time) / 1_000.0,
        "holding_remaining_seconds": (deadline - current_time) / 1_000.0,
    }


def _economics(attempt: Record, state: str, gross_bps: float) -> Record:
    fee = _number(_outcome(attempt, state, "fee_bps"), "ETH current fee")
    funding = _number(_outcome(attempt, state, "funding_bps"), "ETH current funding")
    net = _number(_outcome(attempt, state, "net_return_bps"), "ETH current net")
    pnl = _number(_outcome(attempt, state, "simulated_net_pnl_usd"), "ETH current PnL")
    scope = _text(attempt.get("net_return_scope"), "ETH net return scope")
    notional = _positive_number(attempt.get("entry_notional_usd"), "ETH notional")
    if scope != "exact_depth_fee_and_funding":
        raise ValueError("V58 ETH net return scope is invalid")
    if not _equal(net, gross_bps - fee + funding):
        raise ValueError("V58 ETH net return components do not reconcile")
    if not _equal(pnl, notional * net / 10_000.0):
        raise ValueError("V58 ETH net PnL does not reconcile")
    return {
        "current_fee_bps": fee,
        "current_funding_bps": funding,
        "current_net_break_even_gross_bps": fee - funding,
        "current_net_profit_observed": net > 0.0,
        "current_net_return_bps": net,
        "current_simulated_net_pnl_usd": pnl,
        "net_return_scope": scope,
    }


def _sampled_returns(
    attempt: Record, path: Sequence[Record]
) -> tuple[list[float], list[float]]:
    side = _text(attempt.get("side"), "ETH side")
    entry = _positive_number(attempt.get("entry_price"), "ETH entry price")
    quantity = _positive_number(attempt.get("position_quantity"), "ETH quantity")
    prices = []
    for book in path:
        fill = visible_depth_fill(
            book, position_side=side, notional=0.0, quantity=quantity
        )
        if fill.get("complete") is not True:
            raise ValueError("V58 ETH sampled exit depth is incomplete")
        prices.append(_positive_number(fill.get("price"), "ETH sampled exit price"))
    returns = [directional_return_bps(side, entry, price) for price in prices]
    return returns, prices


def _require_current_outcome(
    attempt: Record, state: str, timestamp: int, price: float, gross: float
) -> None:
    expected = {
        "exit_time_ms": timestamp,
        "exit_price": price,
        "gross_return_bps": gross,
    }
    if any(
        not _equal(_outcome(attempt, state, field), value)
        for field, value in expected.items()
    ):
        raise ValueError("V58 ETH current outcome differs from sampled path")


def _outcome(lifecycle: Record, state: str, field: str) -> object:
    prefix = "current_" if state == "open" else ""
    return lifecycle.get(f"{prefix}{field}")


def _observation_gaps(entry_time: int, path: Sequence[Record]) -> list[int]:
    times = [entry_time, *(book_time(row) for row in path)]
    gaps = [right - left for left, right in zip(times, times[1:])]
    if any(gap <= 0 for gap in gaps):
        raise ValueError("V58 ETH sampled path times are not strictly increasing")
    return gaps


def _nearest_rank(values: Sequence[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    output = tuple(_text(row, label) for row in value)
    if len(output) != len(set(output)):
        raise ValueError(f"{label} must be unique")
    return output


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _number(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(
            float(actual), expected, rel_tol=1e-9, abs_tol=1e-9
        )
    return actual == expected
