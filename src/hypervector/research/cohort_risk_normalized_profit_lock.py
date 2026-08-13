"""Risk-normalized late profit-lock research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    build_fill_index,
    build_funding_index,
)
from hypervector.research.cohort_live_audit_values import mapping, number
from hypervector.research.cohort_open_profit_lock_challenger import (
    build_open_profit_lock_challenger,
)
from hypervector.research.cohort_profit_lock_lifecycle_values import (
    completed_bars,
    lifecycle_economics,
    lifecycle_identity,
    lifecycle_payload,
)
from hypervector.research.cohort_profit_lock_mechanism import (
    build_normalized_profit_lock_report,
)
from hypervector.research.cohort_profit_lock_policy import (
    CandleLike,
    ProfitLockPolicy,
)
from hypervector.research.cohort_profit_lock_results import (
    ProfitLockEconomics,
    build_policy_result,
    withheld_policy,
)
from hypervector.research.cohort_trade_reflection_index import (
    Candle,
    build_reflection_evidence_index,
)

Record = Mapping[str, object]
_POLICY_ID = "r2_floor1_trail1"
_ACTIVATION_R = 2.0
_FLOOR_R = 1.0
_GIVEBACK_R = 1.0
_TREND_POLICY_ID = "r5_floor2_trail2"
_TREND_ACTIVATION_R = 5.0
_TREND_FLOOR_R = 2.0
_TREND_GIVEBACK_R = 2.0
_BPS_DENOMINATOR = 10_000.0


def risk_normalized_policy(
    side: str,
    entry: Record,
    protective_stop: Record,
) -> ProfitLockPolicy:
    """Build one two-R activation, one-R floor, one-R giveback policy."""
    return _policy_from_stop(
        _POLICY_ID,
        _ACTIVATION_R,
        _FLOOR_R,
        _GIVEBACK_R,
        side,
        entry,
        protective_stop,
    )


def trend_runner_policy(
    side: str,
    entry: Record,
    protective_stop: Record,
) -> ProfitLockPolicy:
    """Build one five-R activation, two-R floor, two-R giveback policy."""
    return _policy_from_stop(
        _TREND_POLICY_ID,
        _TREND_ACTIVATION_R,
        _TREND_FLOOR_R,
        _TREND_GIVEBACK_R,
        side,
        entry,
        protective_stop,
    )


def _policy_from_stop(
    policy_id: str,
    activation_r: float,
    floor_r: float,
    giveback_r: float,
    side: str,
    entry: Record,
    protective_stop: Record,
) -> ProfitLockPolicy:
    entry_price = _positive(entry.get("price"), "profit-lock entry price")
    stop_price = _positive(
        protective_stop.get("trigger_price"), "protective stop price"
    )
    direction = _direction(side)
    risk_bps = direction * (entry_price - stop_price) / entry_price * _BPS_DENOMINATOR
    if risk_bps <= 0.0:
        raise ValueError("protective stop must be on the adverse side of entry")
    return ProfitLockPolicy(
        policy_id,
        risk_bps * activation_r,
        risk_bps * floor_r,
        risk_bps * giveback_r,
    )


def build_open_risk_normalized_profit_lock_challenger(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    protective_stop: Record | None,
    marked_economics: Record,
    as_of_ms: int,
) -> dict[str, object]:
    """Describe one open risk-normalized lock without execution authority."""
    if protective_stop is None:
        return _missing_open_stop_report(marked_economics)
    policies = _policies(side, entry, protective_stop)
    report = build_open_profit_lock_challenger(
        candles,
        side,
        entry,
        marked_economics,
        as_of_ms,
        policies=policies,
    )
    report.update(
        {
            "mode": "cohort_open_risk_normalized_profit_lock_challenger_v1",
            "risk_multiple_contract": _risk_multiple_contract(),
            "policy_risk_contracts": _policy_risk_contracts(),
            "policy_origin": "post_hoc_large_winner_giveback_hypothesis_20260813",
            "limitations": _limitations(),
        }
    )
    return report


def _missing_open_stop_report(marked_economics: Record) -> dict[str, object]:
    actual = number(
        marked_economics.get("active_lifecycle_marked_net_pnl_usd"),
        "open marked net PnL",
    )
    return {
        "schema_version": 1,
        "mode": "cohort_open_risk_normalized_profit_lock_challenger_v1",
        "contract": _contract(),
        "status": "withheld_missing_protective_stop",
        "policies": {
            policy_id: _missing_stop_outcome(policy_id, actual)
            for policy_id in _policy_risk_contracts()
        },
        "risk_multiple_contract": _risk_multiple_contract(),
        "policy_risk_contracts": _policy_risk_contracts(),
        "policy_origin": "post_hoc_large_winner_giveback_hypothesis_20260813",
        "limitations": _limitations(),
    }


def build_risk_normalized_profit_lock_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Evaluate the frozen risk-normalized lock across closed live lifecycles."""
    candles = build_reflection_evidence_index(cohort_records).candles
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = [
        _lifecycle_result(trade, candles, fills, funding) for trade in reflected_trades
    ]
    results.sort(key=lambda row: number(row.get("exit_timestamp_ms"), "exit"))
    report = build_normalized_profit_lock_report(
        results,
        policies=_policy_declarations(),
        contract=_contract(),
        limitations=_limitations(),
    )
    report.update(
        {
            "mode": "cohort_risk_normalized_profit_lock_mechanism_v1",
            "mechanism": "two_r_activation_one_r_floor_and_peak_giveback",
            "risk_multiple_contract": _risk_multiple_contract(),
            "policy_risk_contracts": _policy_risk_contracts(),
            "policy_origin": "post_hoc_large_winner_giveback_hypothesis_20260813",
        }
    )
    return report


def _lifecycle_result(
    trade: Record,
    candles: Mapping[str, Mapping[int, Candle]],
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    expected, observed = completed_bars(
        candles.get(identity[1], {}),
        economics.entry_timestamp_ms,
        economics.exit_timestamp_ms,
    )
    complete = len(expected) == len(observed)
    outcomes, initial_risk_bps = _risk_results(
        trade,
        identity[3],
        observed,
        economics,
        symbol_funding,
        complete,
    )
    payload = lifecycle_payload(
        identity,
        economics,
        "eligible" if complete else "insufficient_candle_coverage",
        outcomes,
        expected=len(expected),
        observed=len(observed),
    )
    payload["initial_risk_bps"] = initial_risk_bps
    return payload


def _risk_results(
    trade: Record,
    side: str,
    observed: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    complete: bool,
) -> tuple[dict[str, object], float | None]:
    stop = trade.get("protective_stop")
    if stop is None:
        actual = number(trade.get("net_pnl_usd"), "trade net PnL")
        return {
            policy_id: _missing_stop_outcome(policy_id, actual)
            for policy_id in (_POLICY_ID, _TREND_POLICY_ID)
        }, None
    policies = _policies(
        side, mapping(trade.get("entry"), "trade entry"), mapping(stop, "trade stop")
    )
    outcomes = {
        policy.policy_id: _closed_policy_result(
            policy, side, observed, economics, funding, complete
        )
        for policy in policies
    }
    return outcomes, policies[0].floor_bps


def _closed_policy_result(
    policy: ProfitLockPolicy,
    side: str,
    observed: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    complete: bool,
) -> dict[str, object]:
    if complete:
        return build_policy_result(policy, side, observed, economics, funding)
    return withheld_policy(policy, economics)


def _missing_stop_outcome(
    policy_id: str, actual_net_pnl_usd: float
) -> dict[str, object]:
    return {
        "policy_id": policy_id,
        "activation_bps": None,
        "floor_bps": None,
        "trailing_giveback_bps": None,
        "status": "withheld_missing_protective_stop",
        "activation_timestamp_ms": None,
        "trigger_timestamp_ms": None,
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "actual_net_pnl_usd": actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": None,
    }


def _direction(side: str) -> float:
    if side == "long":
        return 1.0
    if side == "short":
        return -1.0
    raise ValueError("profit-lock side must be long or short")


def _positive(value: object, field: str) -> float:
    parsed = number(value, field)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{field} must be positive and finite")
    return parsed


def _risk_multiple_contract() -> dict[str, float]:
    return {
        "activation_r": _ACTIVATION_R,
        "floor_r": _FLOOR_R,
        "peak_giveback_r": _GIVEBACK_R,
    }


def _policy_risk_contracts() -> dict[str, dict[str, float]]:
    return {
        _POLICY_ID: _risk_multiple_contract(),
        _TREND_POLICY_ID: {
            "activation_r": _TREND_ACTIVATION_R,
            "floor_r": _TREND_FLOOR_R,
            "peak_giveback_r": _TREND_GIVEBACK_R,
        },
    }


def _policy_declarations() -> list[dict[str, object]]:
    return [
        {"policy_id": policy_id, **contract}
        for policy_id, contract in _policy_risk_contracts().items()
    ]


def _policies(
    side: str, entry: Record, protective_stop: Record
) -> tuple[ProfitLockPolicy, ProfitLockPolicy]:
    return (
        risk_normalized_policy(side, entry, protective_stop),
        trend_runner_policy(side, entry, protective_stop),
    )


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "the mechanism was specified after observing open HYPE and SPCX winners",
        "R is the original adverse stop distance and not a volatility forecast",
        "activation and stop updates use prior completed one-minute bars",
        "activation bars cannot trigger a newly created stop",
        "gap-through triggers use the adverse bar open",
        "missing holding candles withhold rather than fabricate an outcome",
        "counterfactual fills reuse actual exit reference ratios and fee rates",
        "overlapping lifecycles are not a shared-portfolio equity path",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
