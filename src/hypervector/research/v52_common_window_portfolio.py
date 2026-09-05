"""Exact opened-window shared-account replay for the v52 route set."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
    adapt_breakout_trades,
    adapt_hulk_payloads,
)
from hypervector.research.evidence_selected_portfolio import PrioritizedPortfolioConfig
from hypervector.research.hype_breakout_exit_models import HypeExitTrade
from hypervector.research.lean_successor_portfolio import (
    EvidenceWindow,
    RouteKey,
    SuccessorVariant,
    apply_incremental_round_trip_cost,
    evaluate_successor_comparison,
)
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome

HULK_ROUTE: RouteKey = ("hulk_expansion_short_robust_v3", "BTC")
SWEEP_ROUTE: RouteKey = ("liquidity_sweep_long_1h_stop60_target60_v2", "BTC")
HYPE_ROUTE: RouteKey = (
    "hype_breakout_compression_alignment_bidirectional_v2",
    "HYPE",
)
COMMON_START_UTC = "2026-07-30T12:00:00+00:00"
COMMON_END_UTC = "2026-08-10T23:00:00+00:00"
_EQUITY_USD = 5_000.0
_NOTIONAL_USD = 5_000.0
_LEVERAGE = 10.0
_ENTRY_FEE_BPS = 4.5
_STRESS_INCREMENT_BPS = 7.0


def build_v52_common_window_portfolio(
    hulk_payload: Mapping[str, object],
    sweep_payload: Mapping[str, object],
    hype_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    """Replay exact opened-window route lifecycles through one v52 account."""
    _validate_hulk_contract(hulk_payload)
    routes = _nominal_routes(hulk_payload, sweep_payload, hype_trades)
    stress = {
        route: apply_incremental_round_trip_cost(
            rows,
            {route: _NOTIONAL_USD},
            incremental_bps=_STRESS_INCREMENT_BPS,
        )
        for route, rows in routes.items()
    }
    artifact = evaluate_successor_comparison(
        {"nominal": routes, "stress": stress},
        _variants(),
        (_common_window(),),
        PrioritizedPortfolioConfig(
            _EQUITY_USD,
            10,
            (HYPE_ROUTE[0], HULK_ROUTE[0], SWEEP_ROUTE[0]),
        ),
    )
    return _attach_contract(artifact)


def _nominal_routes(
    hulk_payload: Mapping[str, object],
    sweep_payload: Mapping[str, object],
    hype_trades: tuple[HypeExitTrade, ...],
) -> dict[RouteKey, tuple[CohortOutcome, ...]]:
    if not hype_trades:
        raise ValueError("v52 common window requires aligned HYPE trades")
    specs = _route_specs()
    return {
        HULK_ROUTE: adapt_hulk_payloads((dict(hulk_payload),), specs[HULK_ROUTE]),
        SWEEP_ROUTE: (_adapt_sweep(sweep_payload, specs[SWEEP_ROUTE]),),
        HYPE_ROUTE: adapt_breakout_trades(hype_trades, specs[HYPE_ROUTE]),
    }


def _adapt_sweep(payload: Mapping[str, object], spec: CohortTradeSpec) -> CohortOutcome:
    selection = _mapping(payload, "selection")
    _validate_sweep_contract(payload, selection)
    target = _number(selection, "target_bps")
    delay = _integer(selection, "maximum_entry_delay_seconds")
    summary = _selected_sweep_row(payload, "grid", target, delay)
    path = _selected_sweep_row(payload, "path_observations", target, delay)
    entry_ms = _integer(path, "entry_time_ms")
    exit_ms = _target_time(path, target)
    net_bps = _number(summary, "mean_net_bps")
    outcome = SharedTradeOutcome(
        trade_id=f"{spec.strategy_id}|BTC|{entry_ms}|forward",
        symbol="BTC",
        entry_time_ms=entry_ms,
        exit_time_ms=exit_ms,
        source_equity_usd=_EQUITY_USD,
        margin_fraction=spec.margin_fraction,
        entry_fee_usd=_NOTIONAL_USD * _ENTRY_FEE_BPS / 10_000.0,
        net_pnl_usd=_NOTIONAL_USD * net_bps / 10_000.0,
        outcome="target_completed",
    )
    return CohortOutcome(spec.strategy_id, "long", outcome)


def _validate_hulk_contract(payload: Mapping[str, object]) -> None:
    if (
        payload.get("execution_authority") != "none"
        or payload.get("report_only") is not True
    ):
        raise ValueError("v52 Hulk evidence must be report-only")
    replay = _mapping(payload, "replay_parameters")
    expected = {
        "target_r_multiple": 3.0,
        "minimum_stop_bps": 20.0,
        "maximum_stop_bps": 75.0,
        "maximum_hold_bars": 48.0,
    }
    for key, value in expected.items():
        if not math.isclose(_number(replay, key), value, abs_tol=1e-9):
            raise ValueError(f"v52 Hulk evidence has wrong {key}")


def _validate_sweep_contract(
    payload: Mapping[str, object], selection: Mapping[str, object]
) -> None:
    if payload.get("execution_authority") != "none":
        raise ValueError("v52 sweep evidence must have no execution authority")
    if payload.get("runtime_strategy_changed") is not False:
        raise ValueError("v52 sweep evidence cannot change runtime strategy")
    contract = _mapping(payload, "contract")
    if not math.isclose(_number(contract, "stop_bps"), 60.0, abs_tol=1e-9):
        raise ValueError("v52 sweep evidence requires a 60 bps stop")
    if not math.isclose(_number(selection, "target_bps"), 60.0, abs_tol=1e-9):
        raise ValueError("v52 sweep evidence requires a 60 bps target")
    if _integer(selection, "maximum_entry_delay_seconds") != 30:
        raise ValueError("v52 sweep evidence requires a 30 second delay")
    if selection.get("forward_path_resolved") is not True:
        raise ValueError("v52 sweep forward path must be resolved")


def _selected_sweep_row(
    payload: Mapping[str, object], key: str, target: float, delay: int
) -> Mapping[str, object]:
    rows = _mapping_rows(payload, key)
    selected = tuple(
        row
        for row in rows
        if row.get("partition") == "forward"
        and _integer(row, "entry_delay_seconds") == delay
        and (key != "grid" or math.isclose(_number(row, "target_bps"), target))
    )
    if len(selected) != 1:
        raise ValueError(f"v52 sweep requires one exact forward {key} row")
    if key == "grid" and (
        _integer(selected[0], "sample_count") != 1
        or _integer(selected[0], "wins") != 1
        or _integer(selected[0], "losses") != 0
        or _integer(selected[0], "timeouts") != 0
    ):
        raise ValueError("v52 sweep forward summary must be one resolved win")
    return selected[0]


def _target_time(path: Mapping[str, object], target: float) -> int:
    targets = _mapping(path, "target_times_ms")
    value = targets.get(str(target), targets.get(target))
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("v52 sweep target time is missing")
    stop = path.get("stop_time_ms")
    if stop is not None and (isinstance(stop, bool) or not isinstance(stop, int)):
        raise ValueError("v52 sweep stop time is malformed")
    if stop is not None and value >= stop:
        raise ValueError("v52 sweep target did not precede stop")
    return value


def _route_specs() -> dict[RouteKey, CohortTradeSpec]:
    return {
        route: CohortTradeSpec(
            route[0], route[1], _NOTIONAL_USD, _LEVERAGE, _ENTRY_FEE_BPS, _EQUITY_USD
        )
        for route in (HULK_ROUTE, SWEEP_ROUTE, HYPE_ROUTE)
    }


def _variants() -> tuple[SuccessorVariant, ...]:
    return (
        SuccessorVariant("btc_hulk_only", (HULK_ROUTE,)),
        SuccessorVariant("btc_specialists", (HULK_ROUTE, SWEEP_ROUTE), "btc_hulk_only"),
        SuccessorVariant(
            "v52_full", (HULK_ROUTE, SWEEP_ROUTE, HYPE_ROUTE), "btc_specialists"
        ),
    )


def _common_window() -> EvidenceWindow:
    return EvidenceWindow(
        "opened_common", _timestamp_ms(COMMON_START_UTC), _timestamp_ms(COMMON_END_UTC)
    )


def _attach_contract(artifact: dict[str, object]) -> dict[str, object]:
    full = artifact["windows"]["opened_common"]["nominal"]["v52_full"]
    seconds = (_timestamp_ms(COMMON_END_UTC) - _timestamp_ms(COMMON_START_UTC)) / 1_000
    artifact.update(
        {
            "schema_version": "v52_common_window_portfolio_v1",
            "runtime_strategy_changed": False,
            "automatic_live_change": False,
            "window_contract": {
                "start_utc": COMMON_START_UTC,
                "end_utc": COMMON_END_UTC,
                "status": "opened_descriptive_not_sealed_oos",
            },
            "observed_cadence": {
                "entries": full["completed_trades"],
                "entries_per_week": full["completed_trades"] / (seconds / 604_800),
            },
            "v52_scope_coverage": _scope_coverage(full),
            "friction_contract": {
                "nominal": "route-native after-cost lifecycle evidence",
                "stress_incremental_round_trip_bps": _STRESS_INCREMENT_BPS,
            },
            "limitations": _limitations(),
        }
    )
    return artifact


def _scope_coverage(full: Mapping[str, object]) -> dict[str, object]:
    configured = {
        f"{HULK_ROUTE[0]}|BTC|short",
        f"{SWEEP_ROUTE[0]}|BTC|long",
        f"{HYPE_ROUTE[0]}|HYPE|long",
        f"{HYPE_ROUTE[0]}|HYPE|short",
    }
    rows = full.get("accepted")
    if not isinstance(rows, tuple) or not all(isinstance(row, Mapping) for row in rows):
        raise RuntimeError("v52 accepted lifecycle projection is malformed")
    observed = {f"{row['strategy_id']}|{row['symbol']}|{row['side']}" for row in rows}
    missing = sorted(configured - observed)
    return {
        "configured_scopes": len(configured),
        "observed_scopes": len(configured & observed),
        "missing_scopes": missing,
        "all_configured_scopes_observed": not missing,
    }


def _limitations() -> list[str]:
    return [
        "The common window was already opened and is descriptive, not sealed OOS.",
        "HYPE alignment was specified after subgroup inspection.",
        "Three completed lifecycles cannot establish repeatability or a profit forecast.",
        "Route-native evidence uses different historical sizing before normalization.",
        "The seven-bps stress is a sensitivity, not measured future adverse selection.",
    ]


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"v52 evidence {key} must be an object")
    return value


def _mapping_rows(
    payload: Mapping[str, object], key: str
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"v52 evidence {key} must be object rows")
    return tuple(value)


def _number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"v52 evidence {key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"v52 evidence {key} must be finite")
    return result


def _integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"v52 evidence {key} must be an integer")
    return value


def _timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("v52 timestamps require UTC offsets")
    return int(parsed.timestamp() * 1_000)
