//! Compact per-strategy performance scoreboard for the default dashboard.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;
use crate::cohort_widgets::{panel, provider_alias, render_empty};

/// Render total and per-strategy lifecycle results from the backend journal.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let Some(performance) = &app.backend.cohort_checkpoint.trade_performance else {
        render_empty(
            frame,
            app,
            area,
            " STRATEGY SCOREBOARD ",
            "Awaiting backend lifecycle results",
        );
        return;
    };
    let current = performance
        .current_run
        .as_ref()
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()));
    let (all_total, all_strategies) = app
        .backend
        .cohort_checkpoint
        .all_time_performance()
        .map_or((&performance.total, &performance.by_strategy), |history| {
            (&history.total, &history.by_strategy)
        });
    let total = std::iter::once(comparison_row(
        "PORTFOLIO",
        current.map(|run| &run.total),
        all_total,
        app,
    ));
    let strategies = all_strategies.iter().map(|(strategy, history)| {
        comparison_row(
            provider_alias(strategy),
            current.and_then(|run| run.by_strategy.get(strategy)),
            history,
            app,
        )
    });
    let title = current.map_or_else(
        || " STRATEGY LEDGER // RUN UNAVAILABLE | ALL-TIME MIXED ".into(),
        |run| {
            let label = if run.total.closed_trades == 0 {
                "FRESH RUN"
            } else {
                "RUN"
            };
            format!(
                " STRATEGY LEDGER // {label} {}/{} | ALL-TIME MIXED ",
                run.total.wins, run.total.losses,
            )
        },
    );
    let mut block = panel(title, app);
    if let Some(annotation) = hulk_entry_quality_annotation(app) {
        block = block.title_bottom(annotation);
    }
    let table = Table::new(
        total.chain(strategies),
        [
            Constraint::Length(14),
            Constraint::Length(5),
            Constraint::Length(4),
            Constraint::Length(7),
            Constraint::Length(5),
            Constraint::Length(4),
            Constraint::Min(7),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new(["STRATEGY", "R W/L", "R%", "RUN $", "A W/L", "A%", "ALL $"])
            .style(app.theme.header),
    )
    .block(block);
    frame.render_widget(table, area);
}

fn hulk_entry_quality_annotation(app: &App) -> Option<Line<'static>> {
    let evidence = app.backend.cohort_checkpoint.hulk_entry_quality.as_ref()?;
    let both = evidence.closed_by_quality.get("flow_and_volume")?;
    let one = evidence.closed_by_quality.get("one_of_two")?;
    let neither = evidence.closed_by_quality.get("neither")?;
    let open = if evidence.open_observations.is_empty() {
        "OPEN 0".into()
    } else {
        let labels = evidence
            .open_observations
            .iter()
            .map(|value| format!("{}:{}", value.symbol, value.quality.to_uppercase()))
            .collect::<Vec<_>>()
            .join(",");
        format!("OPEN {labels}")
    };
    Some(Line::from(vec![
        Span::styled(" HULK Q ANNOTATION ONLY ", app.theme.gold),
        Span::styled(format!("| BOTH {} ", both.trades), app.theme.cyan),
        Span::styled(format!("| ONE {} ", one.trades), app.theme.cyan),
        Span::styled(format!("| NEITHER {} ", neither.trades), app.theme.muted),
        Span::styled(
            format!("{} ", signed_dollars(neither.net_pnl_usd)),
            pnl_style(neither.net_pnl_usd, app),
        ),
        Span::styled(format!("| {open} "), app.theme.coiling),
    ]))
}

fn comparison_row<'a>(
    label: &'a str,
    current: Option<&CohortTradePerformanceSummary>,
    history: &CohortTradePerformanceSummary,
    app: &App,
) -> Row<'a> {
    let mut cells = vec![Cell::from(label).style(pnl_style(history.net_pnl_usd, app))];
    cells.extend(scope_cells(current, app));
    cells.extend(scope_cells(Some(history), app));
    Row::new(cells)
}

fn scope_cells<'a>(value: Option<&CohortTradePerformanceSummary>, app: &App) -> [Cell<'a>; 3] {
    let Some(value) = value else {
        return [
            Cell::from("N/A").style(app.theme.muted),
            Cell::from("-").style(app.theme.muted),
            Cell::from("-").style(app.theme.muted),
        ];
    };
    let style = pnl_style(value.net_pnl_usd, app);
    [
        Cell::from(format!("{}/{}", value.wins, value.losses)),
        Cell::from(
            value
                .win_rate_pct
                .map_or_else(|| "N/A".into(), |number| format!("{number:.0}")),
        ),
        Cell::from(signed_dollars(value.net_pnl_usd)).style(style),
    ]
}

fn pnl_style(value: f64, app: &App) -> Style {
    if value > 0.0 {
        app.theme.bull
    } else if value < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

fn signed_dollars(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}
