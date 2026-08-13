//! Portfolio and per-strategy closed lifecycle performance table.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    style::Style,
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;
use crate::cohort_format::{percent, signed_money};
use crate::cohort_widgets::{panel, provider_alias, render_empty};

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
    let current = performance
        .current_run
        .as_ref()
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()))
        .map(|run| performance_row("CURRENT RUN", &run.total, pnl_style(&run.total, app)));
    let all_time = app
        .backend
        .cohort_checkpoint
        .all_time_performance()
        .map_or((&performance.total, &performance.by_strategy), |value| {
            (&value.total, &value.by_strategy)
        });
    let history = std::iter::once(performance_row("ALL-TIME", all_time.0, app.theme.cyan));
    let strategy_values = all_time.1;
    let strategies = strategy_values.iter().map(|(strategy, summary)| {
        performance_row(provider_alias(strategy), summary, pnl_style(summary, app))
    });
    let cross_provider = app
        .backend
        .cohort_checkpoint
        .user_trade_reflections()
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
    let title = format!(
        "CLOSED PERFORMANCE: MIXED PROFILES // EXACT CONTRACT: SCREEN 6 | PROFILE WINDOW {}T/{profiles}CFG | {} | {run_windows} | XPROV EXITS {cross_provider}/{}",
        performance.total.closed_trades,
        reflection_coverage(
            app.backend.cohort_checkpoint.user_trade_reflections().len(),
            all_time.0.closed_trades,
        ),
        app.backend.cohort_checkpoint.user_trade_reflections().len(),
    );
    let table = Table::new(
        history.chain(current).chain(strategies),
        [
            Constraint::Length(18),
            Constraint::Length(7),
            Constraint::Length(9),
            Constraint::Length(9),
            Constraint::Length(11),
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(8),
            Constraint::Length(10),
            Constraint::Min(10),
        ],
    )
    .column_spacing(1)
    .header(
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
        .style(app.theme.header),
    )
    .block(panel(title.as_str(), app));
    frame.render_widget(table, area);
}

fn performance_row<'a>(
    label: &'a str,
    value: &CohortTradePerformanceSummary,
    style: Style,
) -> Row<'a> {
    Row::new(vec![
        Cell::from(label).style(style),
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
}
