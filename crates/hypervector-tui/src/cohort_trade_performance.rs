//! Portfolio and per-strategy closed lifecycle performance table.

use std::collections::{BTreeMap, BTreeSet};

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    style::Style,
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort::CohortProvider;
use crate::backend_cohort_trade_performance::{
    CohortAllTimeTradePerformance, CohortTradePerformance, CohortTradePerformanceSummary,
};
use crate::cohort_format::{percent, signed_money};
use crate::cohort_widgets::{panel, provider_alias, render_empty};

const FULL_TABLE_MINIMUM_WIDTH: u16 = 145;

/// Render backend-computed totals with one declared return denominator.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let Some(performance) = &app.backend.cohort_checkpoint.trade_performance else {
        render_empty(
            frame,
            app,
            area,
            " CLOSED PERFORMANCE // BACKEND JOURNAL ",
            "Awaiting lifecycle W/L and net-on-margin summaries",
        );
        return;
    };
    let view = performance_view(app, performance);
    if area.width < FULL_TABLE_MINIMUM_WIDTH || area.height < desired_height(app) {
        crate::cohort_trade_performance_compact::render(frame, app, area, performance, &view);
        return;
    }
    let table = Table::new(
        performance_rows(app, performance, &view),
        performance_widths(),
    )
    .column_spacing(1)
    .header(performance_header().style(app.theme.header))
    .block(panel(view.title.as_str(), app));
    frame.render_widget(table, area);
}

fn performance_rows<'a>(
    app: &'a App,
    performance: &'a CohortTradePerformance,
    view: &PerformanceView<'a>,
) -> Vec<Row<'a>> {
    let mut rows = Vec::new();
    if let Some(run) = performance
        .current_run
        .as_ref()
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()))
    {
        rows.push(performance_row(
            "CURRENT RUN",
            &run.total,
            pnl_style(&run.total, app),
        ));
    }
    rows.push(performance_row(
        view.history_label,
        view.history_total,
        app.theme.cyan,
    ));
    if let Some(value) = view.preserved {
        rows.push(performance_row(
            "PRESERVED DATA",
            &value.total,
            pnl_style(&value.total, app),
        ));
    }
    let mut rendered = BTreeSet::new();
    for provider in &app.backend.cohort.providers {
        if !rendered.insert(provider.strategy_id.as_str()) {
            continue;
        }
        let summary = view.history_by_strategy.get(&provider.strategy_id);
        rows.push(provider_performance_row(provider, summary, app));
    }
    rows.extend(
        view.history_by_strategy
            .iter()
            .filter(|(strategy, _)| !rendered.contains(strategy.as_str()))
            .map(|(strategy, summary)| {
                performance_row(provider_alias(strategy), summary, pnl_style(summary, app))
            }),
    );
    rows
}

fn provider_performance_row<'a>(
    provider: &'a CohortProvider,
    summary: Option<&CohortTradePerformanceSummary>,
    app: &App,
) -> Row<'a> {
    let authority = if provider_execution_routes(app, provider) > 0 {
        "E"
    } else {
        "O"
    };
    let value = summary.cloned().unwrap_or_default();
    let label = format!(
        "{} [{authority}/{}]",
        provider_alias(&provider.strategy_id),
        route_sample_tag(&value),
    );
    performance_row(label, &value, pnl_style(&value, app))
}

fn performance_widths() -> [Constraint; 10] {
    [
        Constraint::Length(30),
        Constraint::Length(7),
        Constraint::Length(9),
        Constraint::Length(9),
        Constraint::Length(11),
        Constraint::Length(12),
        Constraint::Length(12),
        Constraint::Length(8),
        Constraint::Length(10),
        Constraint::Min(10),
    ]
}

fn performance_header() -> Row<'static> {
    Row::new([
        "STRATEGY",
        "TRADES",
        "W/L/BE",
        "WIN RATE",
        "NET USD",
        "NET/MARGIN",
        "AVG PNL/TRD",
        "PF",
        "FEES",
        "FUNDING",
    ])
}

pub(crate) struct PerformanceView<'a> {
    pub(crate) history_label: &'static str,
    pub(crate) history_total: &'a CohortTradePerformanceSummary,
    pub(crate) history_by_strategy:
        &'a std::collections::BTreeMap<String, CohortTradePerformanceSummary>,
    pub(crate) preserved: Option<&'a CohortAllTimeTradePerformance>,
    pub(crate) title: String,
}

fn performance_view<'a>(
    app: &'a App,
    performance: &'a CohortTradePerformance,
) -> PerformanceView<'a> {
    let archive = app.backend.cohort_checkpoint.portfolio_archive.as_ref();
    let epoch = archive.and_then(|value| value.accounting_epoch.as_ref());
    let current_run = performance
        .current_run
        .as_ref()
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()));
    let selected = app.backend.cohort_checkpoint.all_time_performance();
    let (history_total, history_by_strategy) = match (epoch, current_run, selected) {
        (Some(_), Some(run), _) => (&run.total, &run.by_strategy),
        (_, _, Some(value)) => (&value.total, &value.by_strategy),
        _ => (&performance.total, &performance.by_strategy),
    };
    let preserved = archive
        .and_then(|value| value.preserved_history.as_ref())
        .map(|value| &value.performance);
    let history_label = if epoch.is_some() {
        "DISPLAY EPOCH"
    } else {
        "ALL-TIME"
    };
    let scope = epoch.map_or_else(
        || "CLOSED PERFORMANCE: MIXED PROFILES".into(),
        |value| {
            let retained = preserved.map_or_else(
                || "UNAVAILABLE".into(),
                |data| format!("{}T", data.total.closed_trades),
            );
            format!(
                "CLOSED PERFORMANCE: {} // DISPLAY EPOCH {} // BACKEND HISTORY PRESERVED {retained}",
                route_coverage(app),
                value.epoch_id,
            )
        },
    );
    PerformanceView {
        history_label,
        history_total,
        history_by_strategy,
        preserved,
        title: performance_title(app, performance, history_total, &scope),
    }
}

fn route_coverage(app: &App) -> String {
    let monitored = app
        .backend
        .cohort
        .providers
        .iter()
        .map(|provider| provider.symbols.len())
        .sum::<usize>();
    let executable = app
        .backend
        .cohort
        .providers
        .iter()
        .map(|provider| provider_execution_routes(app, provider))
        .sum::<usize>();
    format!(
        "{monitored} MONITORED / {executable} EXEC / {} OBS",
        monitored.saturating_sub(executable),
    )
}

pub(crate) fn provider_execution_routes(app: &App, provider: &CohortProvider) -> usize {
    if let Some(symbols) = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .and_then(|generation| generation.current_provider_execution_scopes.as_ref())
        .and_then(|scopes| scopes.get(&provider.strategy_id))
    {
        return provider
            .symbols
            .iter()
            .filter(|symbol| symbols.contains(symbol))
            .count();
    }
    provider.execution_symbols.as_ref().map_or_else(
        || provider.symbols.len(),
        |symbols| {
            provider
                .symbols
                .iter()
                .filter(|symbol| symbols.contains(symbol))
                .count()
        },
    )
}

/// Return enough height to expose aggregate and zero-or-resolved provider rows.
pub(crate) fn desired_height(app: &App) -> u16 {
    let Some(performance) = &app.backend.cohort_checkpoint.trade_performance else {
        return 7;
    };
    let view = performance_view(app, performance);
    let aggregate_rows = usize::from(
        performance
            .current_run
            .as_ref()
            .is_some_and(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str())),
    ) + 1
        + usize::from(view.preserved.is_some());
    let strategy_rows = strategy_row_count(app, view.history_by_strategy);
    u16::try_from(aggregate_rows + strategy_rows + 3).unwrap_or(u16::MAX)
}

/// Return the dense height that exposes every configured route in two columns.
pub(crate) fn compact_height(app: &App) -> u16 {
    let Some(performance) = &app.backend.cohort_checkpoint.trade_performance else {
        return 7;
    };
    let view = performance_view(app, performance);
    crate::cohort_trade_performance_compact::desired_height(app, performance, &view)
}

/// Prefer the dense complete view when full execution columns cannot fit.
pub(crate) fn preferred_height(app: &App, width: u16) -> u16 {
    if width < FULL_TABLE_MINIMUM_WIDTH {
        compact_height(app)
    } else {
        desired_height(app)
    }
}

fn strategy_row_count(
    app: &App,
    history: &BTreeMap<String, CohortTradePerformanceSummary>,
) -> usize {
    app.backend
        .cohort
        .providers
        .iter()
        .map(|provider| provider.strategy_id.as_str())
        .chain(history.keys().map(String::as_str))
        .collect::<BTreeSet<_>>()
        .len()
}

fn performance_title(
    app: &App,
    performance: &CohortTradePerformance,
    history: &CohortTradePerformanceSummary,
    scope: &str,
) -> String {
    let reflections = app.backend.cohort_checkpoint.user_trade_reflections();
    let cross_provider = reflections
        .iter()
        .filter(|trade| trade.cross_provider_exit)
        .count();
    let profiles = performance
        .profile_fingerprint_count
        .map_or_else(|| "N/A".into(), |count| count.to_string());
    let run_windows = performance.process_run_windows.as_ref().map_or_else(
        || "RUN WINDOWS N/A".into(),
        |windows| {
            format!(
                "RUN WINDOWS {} +{}/-{} NOT INDEPENDENT",
                windows.run_count, windows.positive_runs, windows.negative_runs,
            )
        },
    );
    format!(
        "{scope} // EXACT CONTRACT: SCREEN 6 | PROFILE WINDOW {}T/{profiles}CFG | {} | {run_windows} | XPROV EXITS {cross_provider}/{}",
        performance.total.closed_trades,
        reflection_coverage(reflections.len(), history.closed_trades),
        reflections.len(),
    )
}

/// Explain an empty display epoch without implying backend history was deleted.
pub(crate) fn empty_epoch_history_message(app: &App) -> Option<String> {
    let archive = app.backend.cohort_checkpoint.portfolio_archive.as_ref()?;
    archive.accounting_epoch.as_ref()?;
    let retained = archive.preserved_history.as_ref().map_or_else(
        || "UNAVAILABLE".into(),
        |value| {
            let total = &value.performance.total;
            format!(
                "{}/{}/{} ({} CLOSED)",
                total.wins, total.losses, total.breakeven, total.closed_trades,
            )
        },
    );
    Some(format!(
        "DISPLAY EPOCH 0/0 // PRESERVED BACKEND {retained} // RAW FILL LEGS REMAIN BELOW",
    ))
}

fn performance_row<'a>(
    label: impl Into<Cell<'a>>,
    value: &CohortTradePerformanceSummary,
    style: Style,
) -> Row<'a> {
    Row::new(vec![
        label.into().style(style),
        Cell::from(value.closed_trades.to_string()),
        Cell::from(format!(
            "{}/{}/{}",
            value.wins, value.losses, value.breakeven
        )),
        Cell::from(percent(value.win_rate_pct)),
        Cell::from(format!("${}", signed_money(value.net_pnl_usd))).style(style),
        Cell::from(percent(value.net_return_on_margin_pct)).style(style),
        Cell::from(percent(value.mean_trade_return_on_margin_pct)).style(style),
        Cell::from(profit_factor(value.profit_factor, value.closed_trades)),
        Cell::from(format!("${:.2}", value.fees_usd)),
        Cell::from(format!("{:+.4}", value.funding_usd)),
    ])
}

fn profit_factor(value: Option<f64>, closed_trades: usize) -> String {
    if closed_trades == 0 {
        return "N/A".into();
    }
    value.map_or_else(|| "NO LOSS".into(), |number| format!("{number:.2}"))
}

pub(crate) fn route_sample_tag(value: &CohortTradePerformanceSummary) -> &'static str {
    match value.closed_trades {
        0 => "N0",
        1 => "N1",
        2 => "N2",
        _ if value.net_pnl_usd < 0.0 => "NEG3+",
        _ if value.net_pnl_usd > 0.0 => "POS3+",
        _ => "FLAT3+",
    }
}

fn reflection_coverage(reflected: usize, archived: usize) -> String {
    format!("REFLECTIONS {reflected}/{archived}")
}

fn pnl_style(value: &CohortTradePerformanceSummary, app: &App) -> Style {
    if value.net_pnl_usd > 0.0 {
        app.theme.bull
    } else if value.net_pnl_usd < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profit_factor_distinguishes_no_sample_from_no_losses() {
        assert_eq!(profit_factor(None, 0), "N/A");
        assert_eq!(profit_factor(None, 2), "NO LOSS");
        assert_eq!(profit_factor(Some(1.25), 2), "1.25");
    }

    #[test]
    fn reflection_coverage_distinguishes_context_rows_from_archive_closes() {
        assert_eq!(reflection_coverage(50, 53), "REFLECTIONS 50/53");
        assert_eq!(reflection_coverage(53, 53), "REFLECTIONS 53/53");
    }

    #[test]
    fn route_sample_tag_does_not_call_small_samples_repeatable() {
        let mut summary = CohortTradePerformanceSummary {
            closed_trades: 1,
            net_pnl_usd: -10.0,
            ..Default::default()
        };
        assert_eq!(route_sample_tag(&summary), "N1");
        summary.closed_trades = 2;
        assert_eq!(route_sample_tag(&summary), "N2");
        summary.closed_trades = 3;
        assert_eq!(route_sample_tag(&summary), "NEG3+");
    }
}
