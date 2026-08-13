"""Presentation definitions for the v39-to-v45 growth report."""

from __future__ import annotations

JsonMap = dict[str, object]


def _metric(label: str, field: str, fmt: str, *, signed: bool = False) -> JsonMap:
    metric: JsonMap = {"label": label, "field": field, "format": fmt}
    if signed:
        metric["signed"] = True
    return metric


def _card(key: str, dataset: str, source: str, metrics: list[JsonMap]) -> JsonMap:
    return {"id": key, "dataset": dataset, "sourceId": source, "metrics": metrics}


def report_cards() -> list[JsonMap]:
    """Return the three executive metric cards."""
    current = _card(
        "current-card",
        "current_run",
        "v39-checkpoint",
        [
            _metric("Closes", "closed_trades", "number"),
            _metric("Net", "net_pnl_usd", "currency", signed=True),
            _metric("PF", "profit_factor", "number"),
        ],
    )
    all_time = _card(
        "all-time-card",
        "all_time",
        "v39-checkpoint",
        [
            _metric("All-time closes", "closed_trades", "number"),
            _metric("All-time net", "net_pnl_usd", "currency", signed=True),
            _metric("Ex-largest", "net_ex_largest_usd", "currency", signed=True),
        ],
    )
    v45 = _card(
        "v45-card",
        "v45_capacity",
        "v45-stress",
        [
            _metric("Actual slots", "actual_asset_slots", "number"),
            _metric("$5K p99 wave", "p99_stop_wave_usd", "currency"),
            _metric("p99 / equity", "p99_stop_wave_fraction", "percent"),
        ],
    )
    return [current, all_time, v45]


def _all_time_chart() -> JsonMap:
    return {
        "id": "all-time-pnl",
        "title": "All-time route economics are mixed and aggregate-negative",
        "type": "horizontalBar",
        "dataset": "all_time_routes",
        "sourceId": "v39-checkpoint",
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
        "maxRows": 20,
    }


def _regime_chart() -> JsonMap:
    return {
        "id": "regime-accuracy",
        "title": "Pooled regime accuracy weakens after episode de-duplication",
        "type": "bar",
        "dataset": "regime_accuracy",
        "sourceId": "v39-regime",
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


def _risk_chart() -> JsonMap:
    return {
        "id": "v45-slot-risk",
        "title": "$5K modeled p99 stop-wave contribution by asset slot",
        "type": "horizontalBar",
        "dataset": "v45_slot_risk",
        "sourceId": "v45-stress",
        "encodings": {
            "x": {"field": "asset", "type": "nominal"},
            "y": {
                "field": "p99_stop_loss_usd",
                "type": "quantitative",
                "format": "currency",
            },
        },
        "layout": "full",
        "maxRows": 5,
    }


def report_charts() -> list[JsonMap]:
    """Return decision-focused report chart definitions."""
    return [_all_time_chart(), _regime_chart(), _risk_chart()]


def _column(field: str, label: str, fmt: str | None = None) -> JsonMap:
    column: JsonMap = {"field": field, "label": label}
    if fmt is not None:
        column["format"] = fmt
    return column


def _table(
    key: str,
    title: str,
    dataset: str,
    source: str,
    columns: list[JsonMap],
) -> JsonMap:
    return {
        "id": key,
        "title": title,
        "dataset": dataset,
        "sourceId": source,
        "layout": "full",
        "columns": columns,
    }


def _v45_routes_table() -> JsonMap:
    return _table(
        "v45-routes",
        "v45 exact $5K route and exit contract",
        "v45_routes",
        "v45-stress",
        [
            _column("route_label", "Route"),
            _column("planned_notional_usd", "Notional", "currency"),
            _column("risk_contract", "Protection / exit"),
            _column("p99_stop_loss_usd", "p99 stop", "currency"),
        ],
    )


def _current_routes_table() -> JsonMap:
    return _table(
        "current-routes",
        "Every configured v39 route",
        "current_routes",
        "v39-routes",
        [
            _column("route_label", "Route"),
            _column("closed_trades", "Closed"),
            _column("net_pnl_usd", "Net", "currency"),
            _column("v45_action", "v45"),
        ],
    )


def _open_positions_table() -> JsonMap:
    return _table(
        "open-positions",
        "Protected v39 open lifecycles at report cutoff",
        "open_positions",
        "v39-checkpoint",
        [
            _column("position_label", "Position"),
            _column("strategy_label", "Strategy"),
            _column("marked_net_pnl_usd", "Marked net", "currency"),
            _column("protection", "Protection"),
        ],
    )


def report_tables() -> list[JsonMap]:
    """Return exact route and lifecycle table definitions."""
    return [_v45_routes_table(), _current_routes_table(), _open_positions_table()]


def _markdown(key: str, body: str) -> JsonMap:
    return {"id": key, "type": "markdown", "body": body}


def _lead_blocks(generated: str) -> list[JsonMap]:
    return [
        _markdown(
            "title",
            f"# Hypervector v39 → v45 $5,000 Growth Readiness\n\nEvidence cutoff: `{generated}`. v39 remains the active runtime; v45 remains inactive and report-only.",
        ),
        {
            "id": "headline",
            "type": "metric-strip",
            "cardIds": ["current-card", "all-time-card", "v45-card"],
        },
        _markdown(
            "decision",
            "## Decision\n\nKeep v45 at fixed 5x isolated leverage. Use notional—not leverage—as the future adaptive control. The 0.75×/1.00×/1.25× tiers remain counterfactual until compatible v45 after-cost closes demonstrate route-specific repeatability. Do not hot-swap v39 while positions or owned orders remain.",
        ),
        _markdown(
            "why",
            "## Why fixed leverage and variable notional\n\nAt fixed notional, changing leverage changes posted isolated margin and liquidation distance, but not directional PnL, fees, or funding dollars. At fixed margin, raising leverage increases notional and therefore scales both gains and losses while shrinking liquidation headroom. Keeping 5x fixed makes every outcome comparable; varying notional is the auditable way to express stronger or weaker evidence.",
        ),
        {"id": "all-time-chart", "type": "chart", "chartId": "all-time-pnl"},
    ]


def _live_blocks() -> list[JsonMap]:
    return [
        _markdown(
            "live",
            "## Live evidence\n\nThe all-time archive is complete but mixes strategy revisions. Current v39 is separately exact. Aggregate all-time net and leave-largest-winner net are both negative, so capital scaling is not justified by historical headline PnL alone.",
        ),
        {"id": "current-table", "type": "table", "tableId": "current-routes"},
        {"id": "open-table", "type": "table", "tableId": "open-positions"},
        _markdown(
            "successor",
            "## v45 successor\n\nv45 removes Range Onset, HIP-3 Swing, transferred core onset routes, and the broader weak roster. It retains only BTC side-specific specialists, HYPE compression, and SP500 pressure. Ten positions remain account capacity; three assets are the actual simultaneous limit.",
        ),
        {"id": "v45-table", "type": "table", "tableId": "v45-routes"},
        {"id": "risk-chart", "type": "chart", "chartId": "v45-slot-risk"},
        _markdown(
            "risk",
            "The $69.68 p99 stop wave is a deterministic stack of marginal friction estimates at $5,000, not a joint probability or loss ceiling. Gaps, outages, correlated entries, and stop slippage can exceed it. The BTC long target has the thinnest modeled reward after friction and therefore cannot earn the 1.25× tier from readiness alone.",
        ),
    ]


def _closing_blocks() -> list[JsonMap]:
    return [
        _markdown(
            "regime",
            "## Regime detector\n\nThe canonical detector is useful telemetry, conflict attribution, and exit context. Pooled observations overlap; episode onsets are the more honest independence check and remain sparse. No universal regime score is authorized to resize v45.",
        ),
        {"id": "regime-chart", "type": "chart", "chartId": "regime-accuracy"},
        _markdown(
            "validation",
            "## Validation plan\n\nBase tier success means exact v45 route identity, venue stop and deadline coverage, after-cost closes, and no accounting or execution drift. A route can earn 1.25× only after a predeclared compatible window is positive after fees/funding/slippage and remains positive without its largest winner; adverse or technically incomplete evidence maps to 0.75×. These are proposed experiment criteria, not active gates.",
        ),
        _markdown(
            "falsifiers",
            "## Confidence and falsifiers\n\n**High confidence** in the accounting reconciliation, Hyperliquid margin mechanics, and v45 sizing arithmetic. **Medium confidence** that v45 is a cleaner experiment than v39 because demonstrated weak routes were removed. **Low confidence** in v45 profitability because it has no compatible closes. Revise this recommendation if fixed-notional leverage changes measured execution economics, v45 route outcomes remain negative, realized loss exceeds the model materially, or episode-level regime evidence becomes stable enough to support a route-specific sizing interaction.",
        ),
        _markdown(
            "next",
            "## Next actions\n\n1. Let v39 manage its protected open lifecycles to a verified flat/order-free boundary.\n2. Continue v45 observer collection and journal every eligible/non-eligible decision.\n3. Run fresh venue preflight at the transition boundary; request explicit live authority before starting v45.\n4. Start v45 at base notional. Do not activate variable tiers on readiness alone.\n5. Review each compatible close, missed opportunity, regime interaction, and realized friction before accepting 0.75×/1.25× sizing.",
        ),
    ]


def report_blocks(generated: str) -> list[JsonMap]:
    """Return the answer-first narrative in report reading order."""
    return [*_lead_blocks(generated), *_live_blocks(), *_closing_blocks()]
