"""Report-only shared-capital comparison of predeclared route-side variants."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from statistics import median

from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    partition_cohort_outcomes,
)
from hypervector.research.evidence_selected_portfolio import (
    PrioritizedPortfolioConfig,
    replay_prioritized_outcomes,
)

RouteSide = tuple[str, str, str]


@dataclass(frozen=True)
class SidePortfolioVariant:
    """One predeclared set of executable provider-symbol-side components."""

    variant_id: str
    route_sides: tuple[RouteSide, ...]
    strategy_priority: tuple[str, ...]
    maximum_positions: int

    def __post_init__(self) -> None:
        """Reject ambiguous identities, side coverage, and slot contracts."""
        _identity(self.variant_id, "variant_id")
        if not self.route_sides or len(self.route_sides) != len(set(self.route_sides)):
            raise ValueError("route_sides must be non-empty and unique")
        for strategy, symbol, side in self.route_sides:
            _identity(strategy, "route strategy_id")
            _identity(symbol, "route symbol")
            if side not in {"long", "short"}:
                raise ValueError("route side must be long or short")
        strategies = {row[0] for row in self.route_sides}
        if set(self.strategy_priority) != strategies:
            raise ValueError("strategy_priority must exactly cover route strategies")
        if len(self.strategy_priority) != len(set(self.strategy_priority)):
            raise ValueError("strategy_priority identities must be unique")
        if isinstance(self.maximum_positions, bool) or self.maximum_positions < 1:
            raise ValueError("maximum_positions must be a positive integer")
        symbols = {row[1] for row in self.route_sides}
        if self.maximum_positions > len(symbols):
            raise ValueError("maximum_positions exceeds variant symbol count")


def build_side_portfolio_experiment(
    outcomes: tuple[CohortOutcome, ...],
    *,
    variants: tuple[SidePortfolioVariant, ...],
    initial_equity_usd: float,
    development_end_utc: str,
    final_start_utc: str,
    final_end_utc: str,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Compare fixed side variants without selecting or promoting a winner."""
    _positive(initial_equity_usd, "initial_equity_usd")
    if not outcomes:
        raise ValueError("separate-side experiment requires completed outcomes")
    if not variants or len({row.variant_id for row in variants}) != len(variants):
        raise ValueError("separate-side variants must be non-empty and unique")
    _validate_evidence(evidence)
    reports = {
        variant.variant_id: _build_variant(
            outcomes,
            variant,
            initial_equity_usd=initial_equity_usd,
            development_end_utc=development_end_utc,
            final_start_utc=final_start_utc,
            final_end_utc=final_end_utc,
        )
        for variant in variants
    }
    return _artifact(
        reports,
        variants,
        initial_equity_usd=initial_equity_usd,
        development_end_utc=development_end_utc,
        final_start_utc=final_start_utc,
        final_end_utc=final_end_utc,
        evidence=evidence,
    )


def _build_variant(
    outcomes: tuple[CohortOutcome, ...],
    variant: SidePortfolioVariant,
    *,
    initial_equity_usd: float,
    development_end_utc: str,
    final_start_utc: str,
    final_end_utc: str,
) -> dict[str, object]:
    selected = tuple(row for row in outcomes if _route_side(row) in variant.route_sides)
    observed = {_route_side(row) for row in selected}
    missing = sorted(set(variant.route_sides) - observed)
    if missing:
        raise ValueError(
            f"variant {variant.variant_id} lacks route-side outcomes: {missing}"
        )
    partitions = partition_cohort_outcomes(
        selected,
        development_end_utc=development_end_utc,
        holdout_start_utc=final_start_utc,
        holdout_end_utc=final_end_utc,
    )
    _validate_partition_coverage(partitions, variant)
    config = PrioritizedPortfolioConfig(
        initial_equity_usd,
        variant.maximum_positions,
        variant.strategy_priority,
    )
    development = _replay(partitions["development"], config)
    final = _replay(partitions["opened_final_60d"], config)
    combined = _replay(
        partitions["development"] + partitions["opened_final_60d"],
        config,
    )
    return {
        "contract": _variant_contract(variant),
        "input_counts": {
            "development": len(partitions["development"]),
            "opened_final_block": len(partitions["opened_final_60d"]),
            "purged": len(partitions["purged"]),
        },
        "development": development,
        "opened_final_block": final,
        "combined_available_blocks": combined,
    }


def _replay(
    outcomes: tuple[CohortOutcome, ...],
    config: PrioritizedPortfolioConfig,
) -> dict[str, object]:
    if not outcomes:
        raise ValueError("each separate-side evidence block requires outcomes")
    report = replay_prioritized_outcomes(outcomes, config).to_dict()
    accepted = report.get("accepted")
    if not isinstance(accepted, tuple):
        raise RuntimeError("separate-side accepted outcomes are malformed")
    values = tuple(_accepted_net(row) for row in accepted)
    report["concentration"] = _concentration(values)
    report["by_route_side"] = _route_side_attribution(accepted)
    return report


def _validate_partition_coverage(
    partitions: Mapping[str, tuple[CohortOutcome, ...]],
    variant: SidePortfolioVariant,
) -> None:
    required = set(variant.route_sides)
    for key in ("development", "opened_final_60d"):
        observed = {_route_side(row) for row in partitions[key]}
        missing = sorted(required - observed)
        if missing:
            raise ValueError(
                f"variant {variant.variant_id} {key} coverage is missing: {missing}"
            )


def _concentration(values: tuple[float, ...]) -> dict[str, float | int | None]:
    if not values:
        return {
            "trades": 0,
            "median_pnl_usd": None,
            "largest_win_usd": None,
            "largest_loss_usd": None,
            "net_without_largest_win_usd": None,
            "largest_win_share_of_gross_profit_pct": None,
        }
    wins = tuple(value for value in values if value > 0.0)
    losses = tuple(value for value in values if value < 0.0)
    largest_win = max(wins) if wins else None
    gross_profit = sum(wins)
    return {
        "trades": len(values),
        "median_pnl_usd": median(values),
        "largest_win_usd": largest_win,
        "largest_loss_usd": min(losses) if losses else None,
        "net_without_largest_win_usd": (
            sum(values) - largest_win if largest_win is not None else sum(values)
        ),
        "largest_win_share_of_gross_profit_pct": (
            largest_win / gross_profit * 100.0
            if largest_win is not None and gross_profit > 0.0
            else None
        ),
    }


def _route_side_attribution(
    accepted: tuple[object, ...],
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = {}
    for raw in accepted:
        if not isinstance(raw, dict):
            raise RuntimeError("accepted separate-side lifecycle must be an object")
        key = f"{raw['strategy_id']}|{raw['symbol']}|{raw['side']}"
        groups.setdefault(key, []).append(_accepted_net(raw))
    return {key: _summary(values) for key, values in sorted(groups.items())}


def _summary(values: list[float]) -> dict[str, float | int | None]:
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl_usd": sum(values),
        "profit_factor": sum(wins) / sum(losses) if losses else None,
    }


def _accepted_net(value: object) -> float:
    if not isinstance(value, dict):
        raise RuntimeError("accepted separate-side lifecycle must be an object")
    return _finite(value.get("net_pnl_usd"), "accepted net_pnl_usd")


def _route_side(outcome: CohortOutcome) -> RouteSide:
    return (outcome.strategy_id, outcome.outcome.symbol, outcome.side)


def _variant_contract(variant: SidePortfolioVariant) -> dict[str, object]:
    return {
        "route_sides": [list(row) for row in variant.route_sides],
        "strategy_priority": list(variant.strategy_priority),
        "maximum_positions": variant.maximum_positions,
        "one_position_per_symbol": True,
        "shared_realized_equity": True,
        "selection_source": "predeclared_side_evidence",
    }


def _artifact(
    reports: Mapping[str, object],
    variants: tuple[SidePortfolioVariant, ...],
    *,
    initial_equity_usd: float,
    development_end_utc: str,
    final_start_utc: str,
    final_end_utc: str,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_separate_side_shared_portfolio_v1",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": {
            "initial_equity_usd": initial_equity_usd,
            "development_end_exclusive_utc": development_end_utc,
            "purge_minutes": 1_440,
            "opened_final_block_start_utc": final_start_utc,
            "opened_final_block_end_exclusive_utc": final_end_utc,
            "opened_final_block_already_inspected": True,
            "automatic_variant_selection": False,
            "source_friction_scope": (
                "source_lifecycle_net_after_stated_fees_funding_slippage"
            ),
            "friction_recomputed": False,
            "variant_ids": [row.variant_id for row in variants],
        },
        "variants": dict(reports),
        "evidence": dict(evidence),
        "decision": "diagnostic_only_no_runtime_or_promotion_authority",
        "limitations": [
            "the final block was already inspected and is descriptive, not sealed",
            "source lifecycles use their stated friction models and not private IOC queue state",
            "realized-equity drawdown omits concurrent intratrade mark-to-market paths",
            "variant comparison cannot establish future edge or authorize execution",
            "side filtering changes the research hypothesis and is not a free improvement",
        ],
    }


def _identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _validate_evidence(evidence: Mapping[str, object]) -> None:
    if not evidence:
        raise ValueError("separate-side experiment requires immutable evidence")
    hexadecimal = set("0123456789abcdef")
    for name, raw in evidence.items():
        _identity(name, "evidence name")
        if not isinstance(raw, Mapping):
            raise ValueError("evidence entry must be an object")
        sha = raw.get("sha256")
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or any(character not in hexadecimal for character in sha)
        ):
            raise ValueError("evidence requires a lowercase SHA-256 identity")
        size = raw.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("evidence requires a positive byte count")


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
