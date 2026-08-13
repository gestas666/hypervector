//! Compact report-only route, asset, and side evidence frontier.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_side_composition::{CohortSideComponent, CohortSideComposition};
use crate::cohort_widgets::provider_alias;

/// Return the fixed summary footprint when side-composition evidence is present.
pub(crate) fn line_count(evidence: Option<&CohortSideComposition>) -> u16 {
    if evidence.is_some() { 3 } else { 0 }
}

/// Render mixed-profile rankings without implying execution authority or current edge.
pub(crate) fn lines(evidence: &CohortSideComposition, app: &App) -> Vec<Line<'static>> {
    vec![
        Line::from(vec![
            Span::styled("ROUTE-SIDE FRONTIER // REPORT ONLY", app.theme.cyan),
            Span::raw(format!(" // {} COMPONENTS // ", evidence.components)),
            Span::styled(
                "MIXED PROFILE // NOT CURRENT EDGE // NO AUTO SIZE",
                app.theme.gold,
            ),
        ]),
        frontier_line("LONG", evidence.long_frontier.first(), app),
        frontier_line("SHORT", evidence.short_frontier.first(), app),
    ]
}

fn frontier_line(side: &str, component: Option<&CohortSideComponent>, app: &App) -> Line<'static> {
    let side_style = if side == "LONG" {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let Some(component) = component else {
        return Line::from(vec![
            Span::styled(side.to_string(), side_style),
            Span::styled(" FRONTIER UNAVAILABLE", app.theme.muted),
        ]);
    };
    let (strategy, symbol) = component_identity(&component.component);
    let trade_label = if component.trades == 1 {
        "TRADE"
    } else {
        "TRADES"
    };
    let mut spans = vec![
        Span::styled(side.to_string(), side_style),
        Span::raw(format!(
            " {} {} // {} {} // NET {} // USD PF {} // NORM PF {}",
            provider_alias(strategy),
            symbol,
            component.trades,
            trade_label,
            signed_usd(component.net_pnl_usd),
            profit_factor(component.usd_profit_factor),
            profit_factor(component.normalized_profit_factor),
        )),
    ];
    if component.evidence_tension {
        spans.push(Span::styled(" // TENSION", app.theme.gold));
    }
    Line::from(spans)
}

fn component_identity(component: &str) -> (&str, &str) {
    let mut parts = component.rsplitn(3, '|');
    let _side = parts.next();
    let symbol = parts.next().unwrap_or("UNKNOWN");
    let strategy = parts.next().unwrap_or(component);
    (strategy, symbol)
}

fn profit_factor(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}"))
}

fn signed_usd(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}
