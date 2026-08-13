"""Prospective live evidence for one predeclared asymmetric portfolio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from statistics import mean, median

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
RouteSide = tuple[str, str, str]

HYPE_STRATEGY = "hype_breakout_onset_bidirectional_v1"
ETH_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
SOL_STRATEGY = "range_onset_bidirectional_v1"
CANDIDATE_ROUTE_SIDES: tuple[RouteSide, ...] = (
    (HYPE_STRATEGY, "HYPE", "long"),
    (ETH_STRATEGY, "ETH", "long"),
    (SOL_STRATEGY, "SOL", "long"),
    (SOL_STRATEGY, "SOL", "short"),
)
EXCLUDED_SYMMETRIC_ROUTE_SIDES: tuple[RouteSide, ...] = (
    (HYPE_STRATEGY, "HYPE", "short"),
    (ETH_STRATEGY, "ETH", "short"),
)
_SOURCE_ROUTE_SIDES = frozenset(CANDIDATE_ROUTE_SIDES + EXCLUDED_SYMMETRIC_ROUTE_SIDES)
_SOURCE_ROUTES = frozenset(
    (strategy, symbol) for strategy, symbol, _ in _SOURCE_ROUTE_SIDES
)


@dataclass(frozen=True)
class AsymmetricForwardDeclaration:
    """Immutable hypothesis time boundary loaded from journal revision one."""

    predeclared_at_utc: str
    entry_cutoff_timestamp_ms: int

    def __post_init__(self) -> None:
        """Require the text and numeric cutoff identities to agree exactly."""
        cutoff = nonnegative_int(
            self.entry_cutoff_timestamp_ms, "entry cutoff timestamp"
        )
        _cutoff_identity(self.predeclared_at_utc, cutoff)


def load_asymmetric_forward_declaration(
    path: Path,
) -> AsymmetricForwardDeclaration:
    """Load the exact report-only declaration from journal revision one."""
    if not path.is_file():
        raise FileNotFoundError(f"asymmetric forward journal is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("asymmetric forward journal must be an object")
    return asymmetric_forward_declaration(value)


def asymmetric_forward_declaration(
    journal: Mapping[str, object],
) -> AsymmetricForwardDeclaration:
    """Validate and project the frozen revision-one portfolio declaration."""
    if journal.get("hypothesis_id") != "cohort-asymmetric-shared-portfolio":
        raise ValueError("journal hypothesis identity is invalid")
    if journal.get("revision_number") != 1 or journal.get("status") != "candidate":
        raise ValueError("journal must be the frozen candidate revision 1")
    if journal.get("execution_authority") != "none":
        raise ValueError("journal execution authority must be none")
    if journal.get("runtime_strategy_changed") is not False:
        raise ValueError("journal must not report a runtime strategy change")
    declaration = text(journal.get("created_at_utc"), "journal creation time")
    parsed = datetime.fromisoformat(declaration.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("journal creation time must be timezone-aware")
    return AsymmetricForwardDeclaration(declaration, int(parsed.timestamp() * 1_000))


def attach_asymmetric_forward_observer(
    audit: dict[str, object],
    declaration: AsymmetricForwardDeclaration,
) -> None:
    """Attach one prospective observer to a mutable report-only live audit."""
    run = mapping(audit.get("run"), "audit run")
    reflections = mapping(audit.get("trade_reflections"), "trade reflections")
    trades = reflections.get("trades")
    if not isinstance(trades, list) or not all(
        isinstance(row, Mapping) for row in trades
    ):
        raise ValueError("reflected trades must be a list of objects")
    audit["asymmetric_forward_observer"] = build_asymmetric_forward_observer(
        trades,
        current_profile_fingerprint=text(
            run.get("profile_fingerprint"), "profile fingerprint"
        ),
        current_run_id=text(run.get("run_id"), "run id"),
        predeclared_at_utc=declaration.predeclared_at_utc,
        entry_cutoff_timestamp_ms=declaration.entry_cutoff_timestamp_ms,
    )


def build_asymmetric_forward_observer(
    trades: Sequence[Record],
    *,
    current_profile_fingerprint: str,
    current_run_id: str,
    predeclared_at_utc: str,
    entry_cutoff_timestamp_ms: int,
) -> dict[str, object]:
    """Score only exact resolved lifecycles entered after the frozen cutoff."""
    profile = text(current_profile_fingerprint, "current profile fingerprint")
    run_id = text(current_run_id, "current run id")
    cutoff = nonnegative_int(entry_cutoff_timestamp_ms, "entry cutoff timestamp")
    declaration = _cutoff_identity(predeclared_at_utc, cutoff)
    candidate, excluded, counts = _classify_trades(trades, profile, cutoff)
    return {
        "schema_version": 1,
        "mode": "cohort_asymmetric_shared_portfolio_forward_observer_v1",
        "scope": "resolved_venue_lifecycles_entered_at_or_after_predeclared_cutoff",
        "contract": _contract(),
        "hypothesis_id": "cohort-asymmetric-shared-portfolio",
        "selected_variant_id": "sol_symmetric_sensitivity",
        "current_profile_fingerprint": profile,
        "current_run_id": run_id,
        "predeclared_at_utc": declaration,
        "entry_cutoff_timestamp_ms": cutoff,
        "candidate_route_sides": [list(route) for route in CANDIDATE_ROUTE_SIDES],
        "excluded_symmetric_route_sides": [
            list(route) for route in EXCLUDED_SYMMETRIC_ROUTE_SIDES
        ],
        "source_counts": counts,
        "candidate": _grouped_economics(candidate, CANDIDATE_ROUTE_SIDES),
        "excluded_symmetric_sides": _grouped_economics(
            excluded, EXCLUDED_SYMMETRIC_ROUTE_SIDES
        ),
        "evidence_state": (
            "prospective_resolutions_observed"
            if candidate
            else "awaiting_post_cutoff_resolution"
        ),
        "limitations": _limitations(),
    }


def _classify_trades(
    trades: Sequence[Record], profile: str, cutoff: int
) -> tuple[list[Record], list[Record], dict[str, int]]:
    candidate: list[Record] = []
    excluded: list[Record] = []
    counts = {
        "candidate_post_cutoff": 0,
        "excluded_symmetric_post_cutoff": 0,
        "pre_cutoff_in_scope": 0,
        "profile_mismatch_in_scope": 0,
        "unrelated": 0,
    }
    for trade in trades:
        route = _route_side(trade)
        if route[:2] not in _SOURCE_ROUTES:
            counts["unrelated"] += 1
            continue
        entry_ms = _validate_lifecycle(trade)
        if text(trade.get("source_profile_fingerprint"), "trade profile") != profile:
            counts["profile_mismatch_in_scope"] += 1
        elif entry_ms < cutoff:
            counts["pre_cutoff_in_scope"] += 1
        elif route in CANDIDATE_ROUTE_SIDES:
            candidate.append(trade)
            counts["candidate_post_cutoff"] += 1
        elif route in EXCLUDED_SYMMETRIC_ROUTE_SIDES:
            excluded.append(trade)
            counts["excluded_symmetric_post_cutoff"] += 1
        else:
            raise ValueError(f"unclassified source route-side: {_route_key(route)}")
    return candidate, excluded, counts


def _route_side(trade: Record) -> RouteSide:
    side = text(trade.get("side"), "trade side")
    if side not in {"long", "short"}:
        raise ValueError("trade side must be long or short")
    return (
        text(trade.get("strategy_id"), "trade strategy"),
        text(trade.get("symbol"), "trade symbol"),
        side,
    )


def _validate_lifecycle(trade: Record) -> int:
    entry = mapping(trade.get("entry"), "trade entry")
    exit_leg = mapping(trade.get("exit"), "trade exit")
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    if exit_ms <= entry_ms:
        raise ValueError("trade exit must follow entry")
    text(trade.get("source_run_id"), "trade source run")
    for field in ("fees_usd", "funding_usd", "net_pnl_usd"):
        number(trade.get(field), f"trade {field}")
    number(trade.get("net_return_on_margin_pct"), "trade return on margin")
    return entry_ms


def _grouped_economics(
    trades: Sequence[Record], routes: Sequence[RouteSide]
) -> dict[str, object]:
    summary = _economics(trades)
    summary["by_route_side"] = {
        _route_key(route): _economics(
            [trade for trade in trades if _route_side(trade) == route]
        )
        for route in routes
    }
    return summary


def _economics(trades: Sequence[Record]) -> dict[str, object]:
    pnls = tuple(number(trade.get("net_pnl_usd"), "trade net PnL") for trade in trades)
    returns = tuple(
        number(trade.get("net_return_on_margin_pct"), "trade return on margin")
        for trade in trades
    )
    gross_profit = sum(value for value in pnls if value > 0.0)
    gross_loss = -sum(value for value in pnls if value < 0.0)
    largest_win = max((value for value in pnls if value > 0.0), default=None)
    return {
        "closed_trades": len(trades),
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "breakeven": sum(value == 0.0 for value in pnls),
        "net_pnl_usd": sum(pnls),
        "fees_usd": sum(
            number(trade.get("fees_usd"), "trade fees") for trade in trades
        ),
        "funding_usd": sum(
            number(trade.get("funding_usd"), "trade funding") for trade in trades
        ),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "mean_return_on_margin_pct": float(mean(returns)) if returns else None,
        "median_return_on_margin_pct": float(median(returns)) if returns else None,
        "largest_winner_usd": largest_win,
        "net_pnl_excluding_largest_winner_usd": (
            sum(pnls) - largest_win if largest_win is not None else None
        ),
    }


def _cutoff_identity(value: str, expected_ms: int) -> str:
    declaration = text(value, "predeclared timestamp")
    parsed = datetime.fromisoformat(declaration.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("predeclared timestamp must be timezone-aware")
    if int(parsed.timestamp() * 1_000) != expected_ms:
        raise ValueError("predeclared timestamp and entry cutoff disagree")
    return declaration


def _route_key(route: RouteSide) -> str:
    return "|".join(route)


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "actual_resolved_lifecycles_only": True,
        "counterfactual_fills_claimed": False,
        "capital_reallocation_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "only actual resolved venue lifecycles are scored",
        "unfilled and router-displaced opportunities are not simulated",
        "the running profile may allocate capital differently from the candidate",
        "excluded symmetric sides are descriptive controls, not avoided-loss claims",
        "open marks remain provisional and are excluded",
        "the observer cannot route, size, enter, close, pause, or promote a strategy",
    ]
