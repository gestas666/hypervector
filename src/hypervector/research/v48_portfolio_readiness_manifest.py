"""Executive presentation contract for the v48 portfolio-readiness report."""

from __future__ import annotations

from copy import deepcopy

from hypervector.research.v47_strategy_regression_report_manifest import (
    report_cards as v47_cards,
    report_charts as v47_charts,
    report_tables as v47_tables,
)

JsonMap = dict[str, object]


def report_cards() -> list[JsonMap]:
    """Return source-bound headline metrics after the executive summary."""
    cards = deepcopy(v47_cards())
    candidate = next(card for card in cards if card["id"] == "candidate-card")
    candidate["sourceId"] = "v48-stress"
    return cards


def report_charts() -> list[JsonMap]:
    """Return neutral comparison charts for route, risk, and regime evidence."""
    charts = deepcopy(v47_charts())
    route = next(chart for chart in charts if chart["id"] == "all-time-route-pnl")
    route["title"] = "All-time net PnL by provider-symbol route"
    risk = next(chart for chart in charts if chart["id"] == "candidate-slot-risk")
    risk["title"] = "Modeled p99 stop-wave contribution by v48 asset"
    risk["sourceId"] = "v48-stress"
    regime = next(chart for chart in charts if chart["id"] == "regime-accuracy")
    regime["title"] = "Directional accuracy at clustered regime onsets"
    regime["dataset"] = "regime_cluster_accuracy"
    return charts


def report_tables() -> list[JsonMap]:
    """Return exact lookup tables with decision-useful default ordering."""
    tables = deepcopy(v47_tables())
    decisions = next(table for table in tables if table["id"] == "strategy-decisions")
    decisions["defaultSort"] = {"field": "strategy", "direction": "asc"}
    candidate = next(table for table in tables if table["id"] == "candidate-routes")
    candidate["title"] = "v48 route, exit, and sizing contract"
    candidate["sourceId"] = "v48-stress"
    candidate["defaultSort"] = {"field": "route_label", "direction": "asc"}
    open_positions = next(table for table in tables if table["id"] == "open-positions")
    open_positions["defaultSort"] = {"field": "position", "direction": "asc"}
    return tables


def report_blocks(cutoff_label: str) -> list[JsonMap]:
    """Return the answer-first v48 report reading path."""
    return [
        _markdown("title", "# Hypervector $5K Growth Readiness"),
        _executive_summary(cutoff_label),
        {"id": "headline", "type": "metric-strip", "cardIds": _card_ids()},
        _route_finding(),
        {"id": "route-chart", "type": "chart", "chartId": "all-time-route-pnl"},
        _route_implication(),
        _strategy_finding(),
        {"id": "strategy-table", "type": "table", "tableId": "strategy-decisions"},
        _sizing_finding(),
        {"id": "candidate-table", "type": "table", "tableId": "candidate-routes"},
        {"id": "risk-chart", "type": "chart", "chartId": "candidate-slot-risk"},
        _risk_implication(),
        _regime_finding(),
        {"id": "regime-chart", "type": "chart", "chartId": "regime-accuracy"},
        _live_boundary(),
        {"id": "open-table", "type": "table", "tableId": "open-positions"},
        _next_steps(),
        _further_questions(),
        _caveats(),
    ]


def _executive_summary(cutoff: str) -> JsonMap:
    return _markdown(
        "executive-summary",
        "## Executive Summary\n\n"
        "- **Several prior strategies were obscured by defects rather than disproven.** "
        "Range and HYPE retain research/live parity; Hulk's `2R` wording was naming debt, "
        "and Sweep's report overstated resolved evidence.\n"
        "- **The unchanged SP500 and Swing mechanisms do not earn growth capital.** "
        "The SP500 freshness defect was repaired, but the causal v2 route remained negative; "
        "Swing validation was negative without an implementation defect.\n"
        "- **v48 concentrates the $5K trial on four assets at meaningful size.** "
        "BTC, ETH, SOL, and HYPE each use 15% isolated margin at fixed 10x, with a modeled "
        "four-position p99 stop wave of about $294.70.\n"
        f"- **Activation is still conditional.** Evidence cutoff: {cutoff}. The active v39 "
        "owner must reach a verified flat and order-free boundary before v48 can start.",
    )


def _route_finding() -> JsonMap:
    return _markdown(
        "route-finding",
        "## Most historical routes have not demonstrated durable edge\n\n"
        "All-time route results contain real winners, but the portfolio-level history is "
        "mixed across strategy versions and includes confirmed invalid-contract HIP3 v1 "
        "entries. The chart is an accounting map, not a fair ranking of v48 mechanisms.",
        source_id="live-checkpoint",
    )


def _route_implication() -> JsonMap:
    return _markdown(
        "route-implication",
        "**Implication.** Preserve the all-time ledger for accountability, but evaluate v48 "
        "only on exact-profile forward closes and missed qualified setups. Historical mixed "
        "profiles cannot establish v48 expectancy.",
    )


def _strategy_finding() -> JsonMap:
    return _markdown(
        "strategy-finding",
        "## Defect repairs and weak-edge exclusions lead to different actions\n\n"
        "A contract defect calls for a versioned repair; negative economics under a valid "
        "contract calls for removal or a genuinely new mechanism. v48 retains Range, Hulk, "
        "Sweep, and HYPE as forward experiments while excluding SP500 pressure, Swing, HT "
        "onset transfers, and HV Source from the growth roster.",
        source_id="strategy-disposition",
    )


def _sizing_finding() -> JsonMap:
    return _markdown(
        "sizing-finding",
        "## Four meaningful positions replace five weaker allocations\n\n"
        "At $5,000 equity, each v48 asset receives $750 isolated margin and up to $7,500 "
        "notional. Each full position is 1.5x account equity; four occupied assets use 60% "
        "margin and 6x gross account exposure. Each position remains 10x on isolated margin. "
        "Timer exits remain terminal fallbacks behind strategy exits, targets, and protective "
        "stops.",
        source_id="v48-stress",
    )


def _risk_implication() -> JsonMap:
    return _markdown(
        "risk-implication",
        "**Interpretation.** The $294.70 p99 wave is a sampled, stacked stop scenario—not "
        "expected loss, a probability, or a maximum-loss ceiling. Correlated gaps, stop "
        "overrun, and depth cancellation can produce a larger outcome.",
        source_id="v48-stress",
    )


def _regime_finding() -> JsonMap:
    return _markdown(
        "regime-finding",
        "## Regime detection remains attribution, not a leverage multiplier\n\n"
        "Canonical core regime rows are causal and populated, but overlapping pooled samples "
        "and small independent episode counts make headline accuracy unstable. Until route-"
        "specific regime interactions repeat prospectively, regime remains entry/exit context "
        "and conflict attribution rather than an automatic size tier.",
        source_id="regime-forward",
    )


def _live_boundary() -> JsonMap:
    return _markdown(
        "live-boundary",
        "## Existing v39 positions control the transition clock\n\n"
        "The current backend remains the position owner. v48 may be staged in the read-only "
        "cockpit, but it must not replace v39 while any venue position or owned order remains. "
        "The table records the checkpoint-bounded open lifecycles and protection evidence.",
        source_id="live-checkpoint",
    )


def _next_steps() -> JsonMap:
    return _markdown(
        "next-steps",
        "## Recommended next steps\n\n"
        "1. Let v39 manage every protected lifecycle to zero positions and zero owned orders.\n"
        "2. Generate a fresh $5K v48 preflight at that exact boundary.\n"
        "3. Inspect v39-to-v48 identity, routes, sizing, and blockers in the attach-only TUI.\n"
        "4. Start v48 only after explicit live authorization and exact post-start acceptance.\n"
        "5. Review every eligible, withheld, opened, missed, and closed setup after each close.\n"
        "6. Reassess economics on a predeclared forward window with largest-winner sensitivity.",
    )


def _further_questions() -> JsonMap:
    return _markdown(
        "further-questions",
        "## Further questions\n\n"
        "- Does Range preserve after-cost expectancy when ETH and SOL are measured under the "
        "exact v48 context contract?\n"
        "- Does HYPE frequency remain consistent with its frozen compression/onset rules?\n"
        "- Do Hulk and Sweep remain complementary across a full BTC regime cycle?\n"
        "- Can route-specific regime states eventually calibrate size without post-hoc gating?",
    )


def _caveats() -> JsonMap:
    return _markdown(
        "caveats",
        "## Caveats and assumptions\n\n"
        "Profitability confidence is low-to-medium because no exact v48 live closes exist. "
        "Historical artifacts use different windows and strategy identities. The Trade Oracle "
        "was used as a challenger, but its redesign thresholds had no cited source evidence. "
        "Technical acceptance proves identity and protection, not positive expectancy.",
    )


def _card_ids() -> list[str]:
    return ["live-card", "defect-card", "candidate-card"]


def _markdown(key: str, body: str, source_id: str | None = None) -> JsonMap:
    block: JsonMap = {"id": key, "type": "markdown", "body": body}
    if source_id is not None:
        block["sourceId"] = source_id
    return block
