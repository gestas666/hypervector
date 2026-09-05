//! Dense closed-performance view that retains every route on shorter terminals.

use ratatui::{Frame, layout::Rect, text::Line, widgets::Paragraph};

use crate::app::App;
use crate::backend_cohort_trade_performance::{
    CohortTradePerformance, CohortTradePerformanceSummary,
};
use crate::cohort_format::{percent, signed_money};
use crate::cohort_trade_performance::{
    PerformanceView, provider_execution_routes, route_sample_tag,
};
use crate::cohort_widgets::{panel, provider_alias};

/// Render aggregates and every configured route in a bounded two-column grid.
pub(crate) fn render(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    performance: &CohortTradePerformance,
    view: &PerformanceView<'_>,
) {
    let lines = lines(app, performance, view);
    frame.render_widget(
        Paragraph::new(lines).block(panel(view.title.as_str(), app)),
        area,
    );
}

/// Return the rows needed for complete dense route coverage plus panel chrome.
pub(crate) fn desired_height(
    app: &App,
    performance: &CohortTradePerformance,
    view: &PerformanceView<'_>,
) -> u16 {
    let aggregate_rows = aggregate_summaries(app, performance, view).len();
    let route_rows = provider_summaries(app, view).len().div_ceil(2);
    u16::try_from(aggregate_rows + route_rows + 3).unwrap_or(u16::MAX)
}

fn lines<'a>(
    app: &'a App,
    performance: &'a CohortTradePerformance,
    view: &'a PerformanceView<'a>,
) -> Vec<Line<'a>> {
    let mut output = aggregate_summaries(app, performance, view)
        .into_iter()
        .map(Line::from)
        .collect::<Vec<_>>();
    output.push(Line::from(
        "ROUTES // T W/L/BE NET PF FEE // E=EXEC O=OBS N=EPOCH CLOSES",
    ));
    let providers = provider_summaries(app, view);
    for pair in providers.chunks(2) {
        output.push(Line::from(pair.join(" │ ")));
    }
    output
}

fn aggregate_summaries(
    app: &App,
    performance: &CohortTradePerformance,
    view: &PerformanceView<'_>,
) -> Vec<String> {
    let mut output = Vec::new();
    if let Some(run) = performance
        .current_run
        .as_ref()
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()))
    {
        output.push(aggregate("CURRENT RUN", &run.total));
    }
    output.push(aggregate(view.history_label, view.history_total));
    if let Some(preserved) = view.preserved {
        output.push(aggregate("PRESERVED DATA", &preserved.total));
    }
    output
}

fn provider_summaries(app: &App, view: &PerformanceView<'_>) -> Vec<String> {
    app.backend
        .cohort
        .providers
        .iter()
        .map(|provider| {
            let authority = if provider_execution_routes(app, provider) > 0 {
                "E"
            } else {
                "O"
            };
            let value = view
                .history_by_strategy
                .get(&provider.strategy_id)
                .cloned()
                .unwrap_or_default();
            let label = format!(
                "{} [{authority}/{}]",
                provider_alias(&provider.strategy_id),
                route_sample_tag(&value),
            );
            route(&label, &value)
        })
        .collect()
}

fn aggregate(label: &str, value: &CohortTradePerformanceSummary) -> String {
    format!(
        "{label} {}T {}/{}/{} NET ${} RETURN {} PF {} FEES ${:.2} FUND {:+.4}",
        value.closed_trades,
        value.wins,
        value.losses,
        value.breakeven,
        signed_money(value.net_pnl_usd),
        percent(value.net_return_on_margin_pct),
        profit_factor(value),
        value.fees_usd,
        value.funding_usd,
    )
}

fn route(label: &str, value: &CohortTradePerformanceSummary) -> String {
    format!(
        "{label:<24.24} {:>2}T {}/{}/{} ${:>7} P{:>5} F{:>5.2}",
        value.closed_trades,
        value.wins,
        value.losses,
        value.breakeven,
        signed_money(value.net_pnl_usd),
        profit_factor(value),
        value.fees_usd,
    )
}

fn profit_factor(value: &CohortTradePerformanceSummary) -> String {
    if value.closed_trades == 0 {
        return "N/A".into();
    }
    value
        .profit_factor
        .map_or_else(|| "NOLOSS".into(), |number| format!("{number:.2}"))
}
