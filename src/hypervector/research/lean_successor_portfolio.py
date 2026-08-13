"""Fixed-ablation shared-account comparison for a lean successor portfolio."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.evidence_selected_portfolio import (
    PrioritizedPortfolioConfig,
    replay_prioritized_outcomes,
)

RouteKey = tuple[str, str]
RouteOutcomes = Mapping[RouteKey, tuple[CohortOutcome, ...]]


@dataclass(frozen=True)
class SuccessorVariant:
    """One fixed route composition and its additive comparison baseline."""

    variant_id: str
    routes: tuple[RouteKey, ...]
    baseline_variant_id: str | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous portfolio identities or route duplication."""
        if not self.variant_id.strip():
            raise ValueError("successor variant_id must be non-empty")
        if not self.routes or len(self.routes) != len(set(self.routes)):
            raise ValueError("successor variant routes must be non-empty and unique")
        if any(
            not strategy.strip() or not symbol.strip()
            for strategy, symbol in self.routes
        ):
            raise ValueError("successor routes require strategy and symbol identities")
        if self.baseline_variant_id == self.variant_id:
            raise ValueError("successor variant cannot be its own baseline")


@dataclass(frozen=True)
class EvidenceWindow:
    """One half-open entry-time evidence interval or the complete source union."""

    window_id: str
    start_ms: int | None
    end_ms: int | None

    def __post_init__(self) -> None:
        """Require either two causal bounds or an explicitly unbounded window."""
        if not self.window_id.strip():
            raise ValueError("evidence window_id must be non-empty")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("evidence window requires both bounds or neither")
        if self.start_ms is not None and self.end_ms is not None:
            if self.start_ms < 0 or self.end_ms <= self.start_ms:
                raise ValueError("evidence window bounds must be increasing")


def apply_incremental_round_trip_cost(
    outcomes: tuple[CohortOutcome, ...],
    notional_usd: Mapping[RouteKey, float],
    *,
    incremental_bps: float,
) -> tuple[CohortOutcome, ...]:
    """Apply an explicit additional after-cost haircut without changing identity."""
    _nonnegative(incremental_bps, "incremental_bps")
    stressed: list[CohortOutcome] = []
    for row in outcomes:
        route = (row.strategy_id, row.outcome.symbol)
        notional = notional_usd.get(route)
        if notional is None:
            raise ValueError(f"stress notional missing for route: {route}")
        _positive(notional, f"notional_usd[{route}]")
        haircut = notional * incremental_bps / 10_000.0
        source = replace(
            row.outcome,
            net_pnl_usd=row.outcome.net_pnl_usd - haircut,
        )
        stressed.append(CohortOutcome(row.strategy_id, row.side, source))
    return tuple(stressed)


def evaluate_successor_comparison(
    scenarios: Mapping[str, RouteOutcomes],
    variants: tuple[SuccessorVariant, ...],
    windows: tuple[EvidenceWindow, ...],
    config: PrioritizedPortfolioConfig,
) -> dict[str, object]:
    """Evaluate fixed portfolio ablations without execution or promotion authority."""
    _validate_contract(scenarios, variants, windows)
    reports: dict[str, object] = {}
    deltas: dict[str, object] = {}
    for window in windows:
        window_reports = _window_reports(scenarios, variants, window, config)
        reports[window.window_id] = window_reports
        deltas[window.window_id] = {
            friction: _marginal_deltas(result, variants)
            for friction, result in window_reports.items()
        }
    return {
        "schema_version": "lean_successor_portfolio_comparison_v1",
        "mode": "report_only_fixed_route_ablation",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "portfolio_contract": {
            "initial_equity_usd": config.initial_equity_usd,
            "maximum_positions": config.maximum_positions,
            "strategy_priority": config.strategy_priority,
        },
        "variants": [_variant_payload(row) for row in variants],
        "evidence_windows": [_window_payload(row) for row in windows],
        "windows": reports,
        "marginal_deltas": deltas,
    }


def _window_reports(
    scenarios: Mapping[str, RouteOutcomes],
    variants: tuple[SuccessorVariant, ...],
    window: EvidenceWindow,
    config: PrioritizedPortfolioConfig,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for friction, route_rows in sorted(scenarios.items()):
        filtered = {
            route: _filter_window(rows, window) for route, rows in route_rows.items()
        }
        output[friction] = {
            variant.variant_id: _variant_report(variant, filtered, config)
            for variant in variants
        }
    return output


def _variant_report(
    variant: SuccessorVariant,
    route_rows: RouteOutcomes,
    config: PrioritizedPortfolioConfig,
) -> dict[str, object]:
    rows = tuple(row for route in variant.routes for row in route_rows[route])
    if not rows:
        return _unavailable_report(variant)
    report = replay_prioritized_outcomes(rows, config).to_dict()
    accepted = _accepted_rows(report)
    report["by_route"] = _attribution(accepted, include_side=False)
    report["by_route_side"] = _attribution(accepted, include_side=True)
    report["coverage"] = _coverage(accepted, variant.routes)
    report["concentration"] = _concentration(accepted)
    return report


def _unavailable_report(variant: SuccessorVariant) -> dict[str, object]:
    return {
        "status": "no_entries_in_window",
        "completed_trades": 0,
        "net_pnl_usd": 0.0,
        "profit_factor": None,
        "maximum_drawdown_pct": 0.0,
        "coverage": _coverage((), variant.routes),
        "concentration": _concentration(()),
        "execution_authority": "none",
        "report_only": True,
    }


def _filter_window(
    rows: tuple[CohortOutcome, ...],
    window: EvidenceWindow,
) -> tuple[CohortOutcome, ...]:
    if window.start_ms is None or window.end_ms is None:
        return rows
    return tuple(
        row
        for row in rows
        if window.start_ms <= row.outcome.entry_time_ms < window.end_ms
    )


def _accepted_rows(report: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = report.get("accepted")
    if not isinstance(value, tuple):
        raise RuntimeError("successor accepted lifecycle projection is malformed")
    if not all(isinstance(row, Mapping) for row in value):
        raise RuntimeError("successor accepted lifecycle must be an object")
    return value


def _attribution(
    rows: tuple[Mapping[str, object], ...],
    *,
    include_side: bool,
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        key = f"{row['strategy_id']}|{row['symbol']}"
        if include_side:
            key = f"{key}|{row['side']}"
        groups.setdefault(key, []).append(float(row["net_pnl_usd"]))
    return {key: _summary(values) for key, values in sorted(groups.items())}


def _coverage(
    rows: tuple[Mapping[str, object], ...],
    expected_routes: tuple[RouteKey, ...],
) -> dict[str, object]:
    routes = {f"{row['strategy_id']}|{row['symbol']}" for row in rows}
    sides = {f"{row['strategy_id']}|{row['symbol']}|{row['side']}" for row in rows}
    expected = {f"{strategy}|{symbol}" for strategy, symbol in expected_routes}
    expected_sides = {
        f"{strategy}|{symbol}|{side}"
        for strategy, symbol in expected_routes
        for side in ("long", "short")
    }
    return {
        "all_routes_present": expected.issubset(routes),
        "missing_routes": sorted(expected - routes),
        "all_route_sides_present": expected_sides.issubset(sides),
        "missing_route_sides": sorted(expected_sides - sides),
    }


def _concentration(rows: tuple[Mapping[str, object], ...]) -> dict[str, float]:
    values = [float(row["net_pnl_usd"]) for row in rows]
    winners = [value for value in values if value > 0.0]
    largest = max(winners, default=0.0)
    gross_profit = sum(winners)
    return {
        "largest_winner_usd": largest,
        "net_excluding_largest_winner_usd": sum(values) - largest,
        "largest_winner_share_gross_profit_pct": (
            largest / gross_profit * 100.0 if gross_profit else 0.0
        ),
    }


def _summary(values: list[float]) -> dict[str, float | int | None]:
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(values) - len(wins) - len(losses),
        "net_pnl_usd": sum(values),
        "profit_factor": sum(wins) / sum(losses) if losses else None,
    }


def _marginal_deltas(
    reports: Mapping[str, Mapping[str, object]],
    variants: tuple[SuccessorVariant, ...],
) -> dict[str, dict[str, float | int | str | None]]:
    output: dict[str, dict[str, float | int | str | None]] = {}
    for variant in variants:
        if variant.baseline_variant_id is None:
            continue
        candidate = reports[variant.variant_id]
        baseline = reports[variant.baseline_variant_id]
        output[variant.variant_id] = _report_delta(
            candidate,
            baseline,
            variant.baseline_variant_id,
        )
    return output


def _report_delta(
    candidate: Mapping[str, object],
    baseline: Mapping[str, object],
    baseline_variant_id: str,
) -> dict[str, float | int | str | None]:
    return {
        "baseline_variant_id": baseline_variant_id,
        "net_pnl_usd": float(candidate["net_pnl_usd"]) - float(baseline["net_pnl_usd"]),
        "completed_trades": int(candidate["completed_trades"])
        - int(baseline["completed_trades"]),
        "maximum_drawdown_pct": float(candidate["maximum_drawdown_pct"])
        - float(baseline["maximum_drawdown_pct"]),
        "profit_factor": _optional_delta(
            candidate.get("profit_factor"), baseline.get("profit_factor")
        ),
    }


def _optional_delta(candidate: object, baseline: object) -> float | None:
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        return None
    if not isinstance(baseline, (int, float)) or isinstance(baseline, bool):
        return None
    return float(candidate) - float(baseline)


def _variant_payload(variant: SuccessorVariant) -> dict[str, object]:
    return {
        "variant_id": variant.variant_id,
        "routes": variant.routes,
        "baseline_variant_id": variant.baseline_variant_id,
    }


def _window_payload(window: EvidenceWindow) -> dict[str, object]:
    return {
        "window_id": window.window_id,
        "start_ms": window.start_ms,
        "end_ms": window.end_ms,
    }


def _validate_contract(
    scenarios: Mapping[str, RouteOutcomes],
    variants: tuple[SuccessorVariant, ...],
    windows: tuple[EvidenceWindow, ...],
) -> None:
    if set(scenarios) != {"nominal", "stress"}:
        raise ValueError("successor comparison requires nominal and stress scenarios")
    if not variants or len({row.variant_id for row in variants}) != len(variants):
        raise ValueError("successor comparison variants must be non-empty and unique")
    if not windows or len({row.window_id for row in windows}) != len(windows):
        raise ValueError("successor evidence windows must be non-empty and unique")
    available = set(scenarios["nominal"])
    if set(scenarios["stress"]) != available:
        raise ValueError("nominal and stress route identities must match")
    required = {route for variant in variants for route in variant.routes}
    if not required.issubset(available):
        raise ValueError(
            f"successor route evidence is missing: {sorted(required - available)}"
        )
    ids = {row.variant_id for row in variants}
    if any(
        row.baseline_variant_id not in ids
        for row in variants
        if row.baseline_variant_id
    ):
        raise ValueError("successor comparison baseline variant is missing")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value < 0.0:
        raise ValueError(f"{label} must be non-negative and finite")
