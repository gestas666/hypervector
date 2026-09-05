"""Source-bound opportunity and co-trigger reporting for the V58 observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

Record = dict[str, object]
EvaluationKey = tuple[str, str, int]
DirectionKey = tuple[str, str, str]


@dataclass(frozen=True)
class OpportunityContract:
    """Frozen profile identity, asset margins, and executable directions."""

    profile_id: str
    profile_fingerprint: str
    margin_fractions: Mapping[str, float]
    executable_directions: frozenset[DirectionKey]

    def __post_init__(self) -> None:
        """Reject incomplete or unsafe opportunity contracts."""
        if not self.profile_id or not self.profile_fingerprint:
            raise ValueError("opportunity profile identity must be non-empty")
        if not self.margin_fractions:
            raise ValueError("opportunity contract must declare asset margins")
        for symbol, fraction in self.margin_fractions.items():
            if not symbol or not 0.0 < fraction <= 1.0:
                raise ValueError("opportunity margin fractions must be in (0, 1]")


def contract_from_live_config(config: MultiAssetLiveConfig) -> OpportunityContract:
    """Freeze the non-secret sizing and direction contract from a live config."""
    return OpportunityContract(
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        margin_fractions={
            asset.symbol: asset.margin_fraction for asset in config.assets
        },
        executable_directions=config.executable_provider_directions,
    )


def build_opportunity_cotrigger_report(
    rows: Sequence[Mapping[str, object]],
    *,
    contract: OpportunityContract,
    run_id: str,
    source_evidence: Mapping[str, object],
) -> Record:
    """Summarize unique prospective eligibility and same-cycle exposure."""
    cycles = _routing_cycles(rows, contract, run_id)
    observations, co_triggers = _prospective_observations(cycles, contract)
    routes = _route_summaries(observations, contract)
    summary = _summary(observations, co_triggers)
    return {
        "schema_version": 1,
        "generated_at_utc": cycles[-1]["observed_at_utc"],
        "mode": "v58_opportunity_cotrigger_prefix",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "performance_gate": False,
        },
        "identity": {
            "profile_id": contract.profile_id,
            "profile_fingerprint": contract.profile_fingerprint,
            "run_id": run_id,
        },
        "source_evidence": dict(source_evidence),
        "summary": summary,
        "routes": routes,
        "co_trigger_cycles": co_triggers,
        "limitations": _limitations(),
    }


def _routing_cycles(
    rows: Sequence[Mapping[str, object]],
    contract: OpportunityContract,
    run_id: str,
) -> list[Record]:
    if not run_id:
        raise ValueError("opportunity run_id must be non-empty")
    selected: list[Record] = []
    for row in rows:
        if row.get("event_type") != "intent_routing" or row.get("run_id") != run_id:
            continue
        _validate_routing_identity(row, contract)
        selected.append(dict(row))
    if not selected:
        raise ValueError(f"no intent_routing rows found for run_id {run_id}")
    selected.sort(key=lambda row: _integer(row.get("sequence"), "routing sequence"))
    return selected


def _validate_routing_identity(
    row: Mapping[str, object], contract: OpportunityContract
) -> None:
    if row.get("profile_id") != contract.profile_id:
        raise ValueError("routing profile id does not match opportunity contract")
    if row.get("profile_fingerprint") != contract.profile_fingerprint:
        raise ValueError(
            "routing profile fingerprint does not match opportunity contract"
        )
    if row.get("execution_authority") != "none":
        raise ValueError("opportunity source must have execution_authority none")
    _text(row.get("observed_at_utc"), "routing observed_at_utc")
    payload = _mapping(row.get("payload"), "routing payload")
    if not isinstance(payload.get("evaluations"), list):
        raise ValueError("routing evaluations must be a list")


def _prospective_observations(
    cycles: Sequence[Record], contract: OpportunityContract
) -> tuple[list[Record], list[Record]]:
    seen: dict[EvaluationKey, str] = {}
    observations: list[Record] = []
    co_triggers: list[Record] = []
    for cycle in cycles:
        cycle_rows = _new_cycle_observations(cycle, seen, contract)
        observations.extend(cycle_rows)
        eligible = [row for row in cycle_rows if row["executable"] is True]
        if eligible:
            co_triggers.append(_co_trigger_cycle(cycle, eligible, contract))
    return observations, co_triggers


def _new_cycle_observations(
    cycle: Mapping[str, object],
    seen: dict[EvaluationKey, str],
    contract: OpportunityContract,
) -> list[Record]:
    payload = _mapping(cycle.get("payload"), "routing payload")
    evaluations = payload.get("evaluations")
    if not isinstance(evaluations, list):
        raise ValueError("routing evaluations must be a list")
    output: list[Record] = []
    for value in evaluations:
        evaluation = _mapping(value, "provider evaluation")
        if (
            evaluation.get("backend_non_action_reason")
            == "pre_activation_readiness_seed"
        ):
            continue
        observation = _observation(evaluation, cycle, contract)
        signature = json.dumps(evaluation, sort_keys=True, separators=(",", ":"))
        key = _observation_key(observation)
        if key in seen and seen[key] != signature:
            raise ValueError(f"conflicting duplicate provider evaluation: {key}")
        if key not in seen:
            seen[key] = signature
            output.append(observation)
    return output


def _observation(
    evaluation: Mapping[str, object],
    cycle: Mapping[str, object],
    contract: OpportunityContract,
) -> Record:
    strategy = _text(evaluation.get("strategy_id"), "evaluation strategy_id")
    symbol = _text(evaluation.get("symbol"), "evaluation symbol")
    decision = _integer(evaluation.get("decision_time_ms"), "decision_time_ms")
    eligible = _boolean(evaluation.get("eligible"), "evaluation eligible")
    side = _optional_side(evaluation.get("side"))
    if eligible and side is None:
        raise ValueError("eligible provider evaluation must declare a side")
    if symbol not in contract.margin_fractions:
        raise ValueError(
            f"evaluation symbol is absent from opportunity contract: {symbol}"
        )
    executable = (
        eligible and (strategy, symbol, side or "") in contract.executable_directions
    )
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "decision_time_ms": decision,
        "side": side,
        "eligible": eligible,
        "executable": executable,
        "reason": _text(evaluation.get("reason"), "evaluation reason"),
        "decision_action": _text(
            evaluation.get("decision_action"), "evaluation decision_action"
        ),
        "routing_sequence": _integer(cycle.get("sequence"), "routing sequence"),
        "observed_at_utc": _text(cycle.get("observed_at_utc"), "observed_at_utc"),
    }


def _co_trigger_cycle(
    cycle: Mapping[str, object],
    eligible: Sequence[Record],
    contract: OpportunityContract,
) -> Record:
    symbols = sorted({str(row["symbol"]) for row in eligible})
    return {
        "routing_sequence": _integer(cycle.get("sequence"), "routing sequence"),
        "observed_at_utc": _text(cycle.get("observed_at_utc"), "observed_at_utc"),
        "symbols": symbols,
        "eligible_provider_events": len(eligible),
        "margin_fraction": sum(contract.margin_fractions[symbol] for symbol in symbols),
        "events": [
            {
                "strategy_id": row["strategy_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "decision_time_ms": row["decision_time_ms"],
            }
            for row in eligible
        ],
    }


def _route_summaries(
    observations: Sequence[Record], contract: OpportunityContract
) -> dict[str, object]:
    output: dict[str, object] = {}
    for strategy, symbol in sorted(
        {(str(row["strategy_id"]), str(row["symbol"])) for row in observations}
    ):
        selected = [
            row
            for row in observations
            if row["strategy_id"] == strategy and row["symbol"] == symbol
        ]
        eligible = [row for row in selected if row["eligible"] is True]
        executable = [row for row in selected if row["executable"] is True]
        output[f"{strategy}|{symbol}"] = {
            "evaluations": len(selected),
            "eligible_events": len(eligible),
            "executable_eligible_events": len(executable),
            "eligible_by_side": _side_counts(eligible),
            "margin_fraction": contract.margin_fractions[symbol],
            "latest": selected[-1],
        }
    return output


def _summary(
    observations: Sequence[Record],
    co_triggers: Sequence[Record],
) -> Record:
    eligible = [row for row in observations if row["eligible"] is True]
    executable = [row for row in observations if row["executable"] is True]
    maximum_symbols = max((len(row["symbols"]) for row in co_triggers), default=0)
    maximum_margin = max(
        (float(row["margin_fraction"]) for row in co_triggers), default=0.0
    )
    return {
        "routing_cycles": len({row["routing_sequence"] for row in observations}),
        "prospective_evaluations": len(observations),
        "eligible_provider_events": len(eligible),
        "executable_eligible_events": len(executable),
        "observe_only_eligible_events": len(eligible) - len(executable),
        "eligible_symbols": len({row["symbol"] for row in executable}),
        "maximum_concurrent_eligible_symbols": maximum_symbols,
        "maximum_concurrent_margin_fraction": maximum_margin,
    }


def _side_counts(rows: Sequence[Record]) -> Record:
    return {
        "long": sum(row["side"] == "long" for row in rows),
        "short": sum(row["side"] == "short" for row in rows),
    }


def _observation_key(row: Mapping[str, object]) -> EvaluationKey:
    return (
        str(row["strategy_id"]),
        str(row["symbol"]),
        int(row["decision_time_ms"]),
    )


def _limitations() -> list[str]:
    return [
        "This prefix measures observed opportunity, not strategy expectancy or realized fills.",
        "Same-cycle eligibility is descriptive and does not estimate joint signal probability.",
        "Margin fractions are configured maxima; actual notional can be lower after venue sizing.",
        "A short prefix cannot establish stable cadence, side coverage, or correlation.",
        "No result in this report grants execution authority or automatically changes V58.",
    ]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _optional_side(value: object) -> str | None:
    if value is None:
        return None
    if value not in {"long", "short"}:
        raise ValueError("evaluation side must be long, short, or null")
    return str(value)
