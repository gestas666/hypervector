"""Fail-closed current-run execution diagnosis for the V58 research loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

Record = Mapping[str, object]

_NOMINAL_TAKER_SLIPPAGE_PROXY_BPS = 2.0
_V58_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)


def build_v58_execution_quality_diagnostic(checkpoint: Record) -> dict[str, object]:
    """Diagnose execution degradation without acquiring strategy authority."""
    _require_checkpoint_contract(checkpoint)
    audit = _mapping(checkpoint.get("audit"), "audit")
    identity = _identity(audit)
    _require_runtime_health(checkpoint, audit)
    execution = _mapping(audit.get("execution"), "execution")
    timing = _timing(_mapping(audit.get("routing"), "routing"))
    fills = _fill_rows(execution, str(identity["run_id"]))
    outcomes = _submission_outcomes(execution)
    trades = _closed_trades(audit, identity, fills)
    friction = _friction_diagnosis(execution, fills)
    attribution = _closed_attribution(trades, fills)
    sample = _sample(execution, timing, fills, trades, outcomes)
    diagnosis = _diagnosis(sample, friction, attribution)
    return {
        "schema_version": 1,
        "generated_at_utc": _text(checkpoint.get("generated_at_utc"), "generated at"),
        "mode": "report_only_current_run_diagnostic",
        "contract": _report_contract(),
        "live_identity": identity,
        "sample": sample,
        "observed_execution": friction,
        "closed_lifecycle_attribution": attribution,
        "diagnosis": diagnosis,
        "recommendation": _recommendation(diagnosis),
        "uncertainties_and_failure_modes": _uncertainties(sample, attribution),
        "falsifiers": _falsifiers(),
    }


def _identity(audit: Record) -> dict[str, object]:
    run = _mapping(audit.get("run"), "run")
    symbols = _strings(run.get("symbols"), "run symbols")
    if symbols != _V58_SYMBOLS:
        raise ValueError("V58 execution diagnostic asset identity differs")
    fingerprint = _text(run.get("profile_fingerprint"), "profile fingerprint")
    if len(fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in fingerprint
    ):
        raise ValueError("V58 execution diagnostic profile fingerprint is invalid")
    return {
        "run_id": _text(run.get("run_id"), "run id"),
        "profile_id": _text(run.get("profile_id"), "profile id"),
        "profile_fingerprint": fingerprint,
        "symbols": list(symbols),
    }


def _require_checkpoint_contract(checkpoint: Record) -> None:
    contract = _mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_retuning": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("V58 execution diagnostic checkpoint contract is unsafe")


def _require_runtime_health(checkpoint: Record, audit: Record) -> None:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "lifecycle")
    if lifecycle.get("state") != "running_consistent":
        raise ValueError("V58 execution diagnostic backend is not consistent")
    if lifecycle.get("backend_process_health") != "healthy":
        raise ValueError("V58 execution diagnostic backend is not healthy")
    if lifecycle.get("cohort_heartbeat_status") != "running":
        raise ValueError("V58 execution diagnostic heartbeat is not running")
    if lifecycle.get("faulted_assets") != []:
        raise ValueError("V58 execution diagnostic has faulted assets")
    coverage = _mapping(audit.get("coverage"), "coverage")
    if coverage.get("complete") is not True or coverage.get("technical_gaps") != []:
        raise ValueError("V58 execution diagnostic coverage is incomplete")


def _timing(routing: Record) -> dict[str, object]:
    raw = _mapping(routing.get("entry_age_diagnostics"), "entry timing")
    submitted = _nonnegative_integer(raw.get("submitted_entries"), "submitted entries")
    late = _boolean(raw.get("executed_late_entries_proven"), "late entries")
    route_submitted, route_late, headrooms = _route_timing(raw)
    if submitted != route_submitted or late != (route_late > 0):
        raise ValueError("V58 execution diagnostic entry timing is inconsistent")
    return {
        "submitted_entries": submitted,
        "late_submitted_entries": route_late,
        "minimum_submission_headroom_ms": min(headrooms) if headrooms else None,
        "stale_entries_withheld": _nonnegative_integer(
            raw.get("stale_entries_withheld"), "stale entries"
        ),
        "submission_timestamp_observed": _boolean(
            raw.get("submission_timestamp_observed"), "submission timestamp"
        ),
        "entry_submission_enforcement_observed": _boolean(
            raw.get("entry_submission_enforcement_observed"), "entry enforcement"
        ),
    }


def _route_timing(raw: Record) -> tuple[int, int, list[int]]:
    routes = _mapping(raw.get("by_provider_symbol"), "entry timing routes")
    submitted = 0
    late = 0
    headrooms: list[int] = []
    for route, value in routes.items():
        _text(route, "entry timing route")
        row = _mapping(value, f"entry timing route {route}")
        count = _nonnegative_integer(row.get("submitted_entries"), "route submitted")
        route_late = _nonnegative_integer(
            row.get("submitted_entries_over_limit"), "route late"
        )
        if route_late > count:
            raise ValueError("V58 execution diagnostic route late count is invalid")
        submitted += count
        late += route_late
        if count:
            headrooms.append(
                _integer(row.get("minimum_submission_headroom_ms"), "headroom")
            )
    return submitted, late, headrooms


def _fill_rows(execution: Record, run_id: str) -> tuple[Record, ...]:
    history = _records(execution.get("fill_details"), "fill details")
    fills = tuple(
        fill
        for fill in history
        if _text(fill.get("origin_run_id"), "fill origin run") == run_id
    )
    declared = _nonnegative_integer(execution.get("current_run_fills"), "fill count")
    if declared != len(fills):
        raise ValueError("V58 execution diagnostic fill count is inconsistent")
    for fill in fills:
        operation = _text(fill.get("operation"), "fill operation")
        if operation not in {"entry", "protective_stop", "reduce_only_close"}:
            raise ValueError("V58 execution diagnostic fill operation is unsupported")
        _number(fill.get("slippage_bps"), "fill slippage")
        _nonnegative_number(fill.get("acknowledgement_latency_ms"), "fill latency")
    return fills


def _submission_outcomes(execution: Record) -> dict[str, int]:
    raw = _mapping(
        execution.get("current_run_submission_outcomes"), "submission outcomes"
    )
    outcomes = _nonnegative_integer(raw.get("outcomes"), "submission outcomes")
    accepted = _nonnegative_integer(raw.get("accepted"), "accepted submissions")
    rejected = _nonnegative_integer(raw.get("rejected"), "rejected submissions")
    if outcomes != accepted + rejected:
        raise ValueError("V58 execution diagnostic submission totals are inconsistent")
    return {"outcomes": outcomes, "accepted": accepted, "rejected": rejected}


def _closed_trades(
    audit: Record,
    identity: Record,
    fills: Sequence[Record],
) -> tuple[Record, ...]:
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    rows = _records(reflections.get("trades"), "trade reflections")
    fingerprint = identity["profile_fingerprint"]
    current_exits = {
        _fill_exit_identity(fill) for fill in fills if fill.get("operation") != "entry"
    }
    selected = tuple(row for row in rows if _trade_exit_identity(row) in current_exits)
    if any(row.get("source_profile_fingerprint") != fingerprint for row in selected):
        raise ValueError("V58 execution diagnostic trade profile differs")
    selected_exits = [_trade_exit_identity(row) for row in selected]
    if len(selected_exits) != len(set(selected_exits)):
        raise ValueError("V58 execution diagnostic trade exit identity is duplicated")
    for row in selected:
        _text(row.get("lifecycle_id"), "lifecycle id")
        _text(row.get("symbol"), "trade symbol")
        if _text(row.get("side"), "trade side") not in {"long", "short"}:
            raise ValueError("V58 execution diagnostic trade side is invalid")
        _number(row.get("net_pnl_usd"), "trade net PnL")
    return selected


def _fill_exit_identity(fill: Record) -> tuple[str, int]:
    return (
        _text(fill.get("symbol"), "fill symbol"),
        _integer(fill.get("venue_timestamp_ms"), "fill venue timestamp"),
    )


def _trade_exit_identity(trade: Record) -> tuple[str, int]:
    exit_fill = _mapping(trade.get("exit"), "trade exit")
    return (
        _text(trade.get("symbol"), "trade symbol"),
        _integer(exit_fill.get("venue_timestamp_ms"), "trade exit timestamp"),
    )


def _friction_diagnosis(
    execution: Record,
    fills: Sequence[Record],
) -> dict[str, object]:
    friction = _mapping(execution.get("friction_parity"), "friction parity")
    summary = _mapping(friction.get("summary"), "friction summary")
    rows = _mapping(friction.get("by_provider_symbol"), "friction routes")
    entry_slippage = _current_entry_slippage(fills)
    comparisons: list[dict[str, object]] = []
    degradation = False
    for route, slippages in sorted(entry_slippage.items()):
        row = _mapping(rows.get(route), f"friction route {route}")
        modeled = _mapping(row.get("modeled_contract"), f"modeled contract {route}")
        delta = sum(slippages) / len(slippages) - _number(
            modeled.get("entry_slippage_bps"), "modeled entry slippage"
        )
        mismatches = row.get("mismatches")
        if not isinstance(mismatches, list):
            raise ValueError("V58 execution diagnostic mismatches are invalid")
        aligned = row.get("parity_state") == "runtime_shape_aligned" and not mismatches
        degradation |= not aligned or delta > 0.0
        comparisons.append(
            {
                "route": route,
                "fills": len(slippages),
                "slippage_mean_minus_modeled_bps": delta,
                "runtime_shape_aligned": aligned,
            }
        )
    return {
        "entry_route_comparisons": comparisons,
        "entry_execution_degradation_supported": degradation,
        "friction_summary": dict(summary),
        "current_run_entry_routes": len(comparisons),
    }


def _current_entry_slippage(fills: Sequence[Record]) -> dict[str, list[float]]:
    output: dict[str, list[float]] = {}
    for fill in fills:
        if fill.get("operation") != "entry":
            continue
        strategy = _text(fill.get("strategy_id"), "entry strategy")
        symbol = _text(fill.get("symbol"), "entry symbol")
        output.setdefault(f"{strategy}|{symbol}", []).append(
            _number(fill.get("slippage_bps"), "entry slippage")
        )
    return output


def _closed_attribution(
    trades: Sequence[Record],
    fills: Sequence[Record],
) -> dict[str, object]:
    pnls = [_number(row.get("net_pnl_usd"), "trade net PnL") for row in trades]
    total = sum(pnls)
    stop_slippage = [
        _number(row.get("slippage_bps"), "stop slippage")
        for row in fills
        if row.get("operation") == "protective_stop"
    ]
    winner = max((pnl for pnl in pnls if pnl > 0.0), default=None)
    return {
        "net_pnl_usd": total,
        "largest_winner_usd": winner,
        "net_pnl_excluding_largest_winner_usd": (
            total - winner if winner is not None else total
        ),
        "sides_observed": sorted(
            {_text(row.get("side"), "trade side") for row in trades}
        ),
        "stop_exit_slippage_bps": _metric(stop_slippage),
        "stop_slippage_comparison_proxy_bps": _NOMINAL_TAKER_SLIPPAGE_PROXY_BPS,
    }


def _sample(
    execution: Record,
    timing: Record,
    fills: Sequence[Record],
    trades: Sequence[Record],
    outcomes: Record,
) -> dict[str, object]:
    return {
        "submitted_entries": timing["submitted_entries"],
        "entry_fills": sum(row.get("operation") == "entry" for row in fills),
        "all_fills": len(fills),
        "closed_lifecycles": len(trades),
        "open_lifecycles": _nonnegative_integer(
            execution.get("open_lifecycles"), "open lifecycles"
        ),
        "rejected_submissions": outcomes["rejected"],
        "late_submitted_entries": timing["late_submitted_entries"],
        "minimum_submission_headroom_ms": timing["minimum_submission_headroom_ms"],
    }


def _diagnosis(
    sample: Record, friction: Record, attribution: Record
) -> dict[str, object]:
    entry_degraded = bool(friction["entry_execution_degradation_supported"])
    entry_degraded |= sample["rejected_submissions"] != 0
    entry_degraded |= sample["late_submitted_entries"] != 0
    stop_metric = _mapping(attribution["stop_exit_slippage_bps"], "stop metric")
    stop_maximum = stop_metric.get("maximum")
    stop_tail = (
        isinstance(stop_maximum, (int, float))
        and stop_maximum > _NOMINAL_TAKER_SLIPPAGE_PROXY_BPS
    )
    primary = (
        "execution_degradation_observed"
        if entry_degraded
        else "insufficient_sample_path_variance"
    )
    if not entry_degraded and stop_tail:
        primary = "insufficient_sample_path_variance_with_stop_exit_cost_tail"
    return {
        "primary_attribution": primary,
        "entry_execution_degradation_supported": entry_degraded,
        "stop_exit_cost_tail_observed": stop_tail,
        "strategy_breakage_supported": False,
        "live_change_supported": False,
        "confidence": "medium_execution_low_strategy",
    }


def _recommendation(diagnosis: Record) -> dict[str, object]:
    return {
        "decision": "retain_v58_unchanged_continue_exact_lifecycle_collection",
        "why_now": "current losses require execution-versus-path attribution",
        "proposed_live_change": None,
        "explicit_approval_requested": False,
        "next_investigation": (
            "reconcile the authoritative exits of the two current open lifecycles; "
            "continue stop-slippage measurement on subsequent exact closes"
        ),
        "entry_execution_degradation_supported": diagnosis[
            "entry_execution_degradation_supported"
        ],
    }


def _uncertainties(sample: Record, attribution: Record) -> list[str]:
    sides = attribution.get("sides_observed")
    if not isinstance(sides, list):
        raise ValueError("V58 execution diagnostic observed sides must be a list")
    stop_metric = _mapping(attribution.get("stop_exit_slippage_bps"), "stop metric")
    stop_count = _nonnegative_integer(stop_metric.get("count"), "stop count")
    stop_unit = "observation" if stop_count == 1 else "observations"
    return [
        (
            f"{sample['entry_fills']} current-process entries and "
            f"{sample['closed_lifecycles']} resolved lifecycles across "
            f"{len(sides)} sides cannot establish route expectancy"
        ),
        (
            f"stop slippage has {stop_count} {stop_unit} and the two-bps "
            "comparison is a research proxy"
        ),
        "open lifecycle PnL is excluded from realized performance attribution",
        "negative largest-winner-removed net establishes concentration, not strategy invalidity",
    ]


def _falsifiers() -> list[str]:
    return [
        "a submitted entry is shown to exceed its exact configured age limit",
        "submission rejection or runtime-contract mismatch is missing from the checkpoint",
        "recomputed fill, fee, funding, slippage, or lifecycle PnL differs from the source ledger",
        "a larger both-side source-compatible sample attributes losses to stable execution degradation",
        "the checkpoint identity or coverage is stale, inconsistent, or technically incomplete",
    ]


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _metric(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"count": 0, "mean": None, "minimum": None, "maximum": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 execution diagnostic {label} must be an object")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"V58 execution diagnostic {label} must be an object array")
    return tuple(value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"V58 execution diagnostic {label} must be a string array")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"V58 execution diagnostic {label} must be text")
    return value


def _number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"V58 execution diagnostic {label} must be finite")
    return float(value)


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"V58 execution diagnostic {label} must be nonnegative")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"V58 execution diagnostic {label} must be an integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    integer = _integer(value, label)
    if integer < 0:
        raise ValueError(f"V58 execution diagnostic {label} must be nonnegative")
    return integer


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"V58 execution diagnostic {label} must be boolean")
    return value
