"""Presentation contract for the v47 strategy-regression report."""

from __future__ import annotations

JsonMap = dict[str, object]


def _column(field: str, label: str, fmt: str | None = None) -> JsonMap:
    column: JsonMap = {"field": field, "label": label}
    if fmt is not None:
        column["format"] = fmt
    return column


def _metric(label: str, field: str, fmt: str, *, signed: bool = False) -> JsonMap:
    metric: JsonMap = {"label": label, "field": field, "format": fmt}
    if signed:
        metric["signed"] = True
    return metric


def _card(key: str, dataset: str, source: str, metrics: list[JsonMap]) -> JsonMap:
    return {"id": key, "dataset": dataset, "sourceId": source, "metrics": metrics}


def report_cards() -> list[JsonMap]:
    """Return the executive evidence cards."""
    return [
        _card(
            "live-card",
            "all_time",
            "live-checkpoint",
            [
                _metric("All-time closes", "closed_trades", "number"),
                _metric("Net", "net_pnl_usd", "currency", signed=True),
                _metric("PF", "profit_factor", "number"),
            ],
        ),
        _card(
            "defect-card",
            "defect_summary",
            "hip3-parity",
            [
                _metric("Invalid-contract closes", "affected_closed_trades", "number"),
                _metric(
                    "Attributed net", "affected_net_pnl_usd", "currency", signed=True
                ),
                _metric("Run-loss share", "affected_loss_fraction", "percent"),
            ],
        ),
        _card(
            "candidate-card",
            "candidate_capacity",
            "v47-stress",
            [
                _metric("Usable assets", "usable_asset_slots", "number"),
                _metric("$5K p99 wave", "p99_stop_wave_loss_usd", "currency"),
                _metric("p99 / equity", "p99_stop_wave_fraction", "percent"),
            ],
        ),
    ]


def _route_chart() -> JsonMap:
    return {
        "id": "all-time-route-pnl",
        "title": "All-time route PnL exposes both survivors and broken transfers",
        "type": "horizontalBar",
        "dataset": "all_time_routes",
        "sourceId": "live-checkpoint",
        "encodings": {
            "x": {"field": "route_label", "type": "nominal"},
            "y": {
                "field": "net_pnl_usd",
                "type": "quantitative",
                "format": "currency",
            },
        },
        "referenceLines": [{"axis": "y", "value": 0, "label": "Breakeven"}],
        "layout": "full",
        "maxRows": 24,
    }


def _risk_chart() -> JsonMap:
    return {
        "id": "candidate-slot-risk",
        "title": "$5K modeled p99 stop-wave contribution by asset",
        "type": "horizontalBar",
        "dataset": "candidate_slot_risk",
        "sourceId": "v47-stress",
        "encodings": {
            "x": {"field": "asset", "type": "nominal"},
            "y": {
                "field": "p99_stop_loss_usd",
                "type": "quantitative",
                "format": "currency",
            },
        },
        "layout": "full",
        "maxRows": 8,
    }


def _regime_chart() -> JsonMap:
    return {
        "id": "regime-accuracy",
        "title": "Regime accuracy: pooled, onset, and clustered observations",
        "type": "bar",
        "dataset": "regime_accuracy",
        "sourceId": "regime-forward",
        "encodings": {
            "x": {"field": "horizon", "type": "ordinal"},
            "y": {"field": "accuracy_pct", "type": "quantitative", "unit": "%"},
            "color": {"field": "series", "type": "nominal"},
        },
        "referenceLines": [
            {"axis": "y", "value": 50, "label": "Chance", "lineStyle": "dashed"}
        ],
        "layout": "full",
        "maxRows": 20,
    }


def report_charts() -> list[JsonMap]:
    """Return the decision-supporting visual definitions."""
    return [_route_chart(), _risk_chart(), _regime_chart()]


def report_tables() -> list[JsonMap]:
    """Return the strategy, route, and open-lifecycle tables."""
    return [
        {
            "id": "strategy-decisions",
            "title": "Strategy diagnosis and disposition",
            "dataset": "strategy_decisions",
            "sourceId": "strategy-disposition",
            "layout": "full",
            "columns": [
                _column("strategy", "Strategy"),
                _column("diagnosis", "Diagnosis"),
                _column("evidence", "Observed evidence"),
                _column("decision", "Decision"),
                _column("confidence", "Confidence"),
            ],
        },
        {
            "id": "candidate-routes",
            "title": "v47 route, exit, and sizing contract",
            "dataset": "candidate_routes",
            "sourceId": "v47-stress",
            "layout": "full",
            "columns": [
                _column("route_label", "Route"),
                _column("timeframe", "TF"),
                _column("sides", "Sides"),
                _column("notional_usd", "Notional", "currency"),
                _column("risk_contract", "Stop / primary exit / fallback"),
            ],
        },
        {
            "id": "open-positions",
            "title": "Live v39 positions at report cutoff",
            "dataset": "open_positions",
            "sourceId": "live-checkpoint",
            "layout": "full",
            "columns": [
                _column("position", "Position"),
                _column("strategy_label", "Strategy"),
                _column("marked_net_pnl_usd", "Marked net", "currency"),
                _column("protection", "Protection"),
                _column("contract_note", "Contract note"),
            ],
        },
    ]


def _markdown(key: str, body: str) -> JsonMap:
    return {"id": key, "type": "markdown", "body": body}


def _lead_blocks(cutoff: str) -> list[JsonMap]:
    return [
        _markdown(
            "title",
            f"# Hypervector Strategy Regression and v47 Repair Plan\n\nEvidence cutoff: `{cutoff}`. Active v39 remains live; v47 is staged report-only.",
        ),
        {
            "id": "headline",
            "type": "metric-strip",
            "cardIds": ["live-card", "defect-card", "candidate-card"],
        },
        _markdown(
            "technical-summary",
            "## Technical summary\n\nThe evidence does **not** support treating every prior strategy as bad. One material live/research mismatch is confirmed: HIP-3 v1 accepted 30-second-old pressure while the archive contract allowed 15 seconds. Range Onset inactivity is statistically plausible for a sparse signal, and the BTC/HYPE survivors retain limited positive evidence. Conversely, unchanged ETH/SOL HT-onset transfers and commodity Swing routes remain negative or winner-concentrated after friction. v47 repairs the confirmed contract, restores selected sparse mechanisms, removes weak transfers, and increases meaningful exposure with fixed 10x leverage and 12% margin per asset.",
        ),
        {"id": "route-chart", "type": "chart", "chartId": "all-time-route-pnl"},
        _markdown(
            "scope",
            "## Scope, data, and definitions\n\nThis report reconciles the fresh live checkpoint, immutable research artifacts, the versioned HIP-3 parity journal, the v47 TOML contract, and its venue-friction stress. A **defect** means live behavior violated the frozen researched contract. **Weak edge** means the tested contract itself was negative or unstable. **Sparse-valid** means infrequent signals are consistent with the mechanism and absence of trades is not evidence of a runtime failure.",
        ),
        {"id": "strategy-table", "type": "table", "tableId": "strategy-decisions"},
    ]


def _body_blocks() -> list[JsonMap]:
    return [
        _markdown(
            "methodology",
            "## Methodology\n\nEach strategy was traced through provider identity, entry decision, live eligibility, execution contract, exits, fees, funding, and chronological evidence. Arithmetic was reconciled to the live route totals. Robustness checks prioritize chronological folds and results after removing the largest winner. No performance threshold silently grants or removes execution authority; dispositions describe the next experiment.",
        ),
        _markdown(
            "candidate",
            "## Repaired $5K candidate\n\nv47 contains six routes across five assets. Ten positions remain account capacity, but one-position-per-asset routing makes five the current simultaneous maximum. Each filled asset uses 12% isolated margin and 10x leverage, or $6,000 notional at $5,000 equity. Mechanism-specific exits are preserved; timer exits remain secondary fallbacks.",
        ),
        {"id": "candidate-table", "type": "table", "tableId": "candidate-routes"},
        {"id": "risk-chart-block", "type": "chart", "chartId": "candidate-slot-risk"},
        _markdown(
            "limitations",
            "## Limitations and robustness\n\nThe 5.74% modeled p99 stop wave is a stack of marginal venue-friction estimates, not a joint probability or loss ceiling. Gaps, depth cancellation, correlated entries, and stop slippage can exceed it. v47 has no compatible live closes, ETH's range context change is post-hoc, HYPE confirmation has four trades and becomes negative without its largest winner, and SP500 uses limited/proxy exit evidence. These facts reduce confidence but do not justify reverting to known-bad transfers.",
        ),
        _markdown(
            "regime",
            "## Regime detector\n\nCanonical core regime telemetry is causal and populated, but pooled observations overlap and independent episode counts remain sparse. HIP-3 still lacks canonical regime parity. Regime is therefore retained as telemetry, conflict attribution, and exit context—not a universal entry veto or leverage multiplier.",
        ),
        {"id": "regime-chart-block", "type": "chart", "chartId": "regime-accuracy"},
        {"id": "open-table", "type": "table", "tableId": "open-positions"},
        _markdown(
            "next",
            "## Next steps\n\n1. Let v39 manage every protected open lifecycle to a verified flat, order-free boundary.\n2. Generate a fresh v47 preflight and stage its exact fingerprint in the TUI.\n3. Start v47 only with explicit live-risk authorization; journal every eligible, withheld, opened, and closed event.\n4. Compare realized fill, fee, funding, stop, and deadline behavior with the stress model after every close.\n5. Treat a first close as plumbing evidence. Reassess economics only after a predeclared compatible window and largest-winner sensitivity.\n6. Investigate missed qualified signals as aggressively as losses so overly restrictive gates are visible.",
        ),
        _markdown(
            "questions",
            "## Further questions\n\nThe main unknown is whether the repaired mechanisms retain edge at the larger notional under actual co-triggering and slippage. Confidence is **high** that HIP-3 v1 violated its contract and that v47 removes the weak HT transfers; **medium** that Range Onset and BTC Hulk deserve renewed forward testing; **low-to-medium** that the full v47 portfolio will be profitable before compatible live outcomes exist. Falsifiers include fresh15 HIP-3 entries reproducing the same losses, Range Onset remaining negative across independent periods, realized stop waves materially exceeding the model, or v47 route outcomes remaining negative after complete friction.",
        ),
    ]


def report_blocks(cutoff: str) -> list[JsonMap]:
    """Return the answer-first technical narrative."""
    return [*_lead_blocks(cutoff), *_body_blocks()]
