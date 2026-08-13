//! Exact venue-fill modal for the cohort trade workspace.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    text::{Line, Span},
    widgets::{Clear, Paragraph},
};

use crate::app::App;
use crate::backend_cohort::CohortFill;
use crate::cohort_format::{fill_time, money, optional_bps};
use crate::cohort_widgets::{panel, provider_alias};

/// Render the currently selected exact venue fill.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let display_index = app
        .selected_cohort_fill_index
        .min(app.backend.cohort.fills.len().saturating_sub(1));
    let Some(index) = app
        .backend
        .cohort
        .fills
        .len()
        .checked_sub(display_index + 1)
    else {
        return;
    };
    let Some(fill) = app.backend.cohort.fills.get(index) else {
        return;
    };
    let modal = centered_rect(82, 70, area);
    frame.render_widget(Clear, modal);
    frame.render_widget(
        Paragraph::new(fill_detail_lines(fill, app))
            .block(panel(" FILL INSPECTOR // VENUE EVIDENCE ", app)),
        modal,
    );
}

fn fill_detail_lines<'a>(fill: &'a CohortFill, app: &App) -> Vec<Line<'a>> {
    let mut lines = fill_execution_lines(fill, app);
    lines.extend(lifecycle_detail_lines(fill));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "[Enter/Esc] CLOSE",
        app.theme.muted,
    )));
    lines
}

fn fill_execution_lines<'a>(fill: &'a CohortFill, app: &App) -> Vec<Line<'a>> {
    vec![
        Line::from(vec![
            Span::styled(
                format!("{} {}", fill.symbol, fill.direction),
                app.theme.title,
            ),
            Span::raw(format!("  //  {}", provider_alias(&fill.strategy_id))),
        ]),
        Line::from(format!("SCOPE {}", fill_scope(fill, app))),
        Line::from(format!(
            "VENUE TIME {}  //  OPERATION {}",
            fill_time(fill.venue_timestamp_ms),
            fill.operation
        )),
        Line::from(format!(
            "TRADE ID {}  //  ORDER ID {}",
            fill.trade_id, fill.oid
        )),
        Line::from(format!(
            "ORIGIN RUN {}",
            fill.origin_run_id.as_deref().unwrap_or("NOT RECORDED")
        )),
        Line::from(format!(
            "PRICE {:.8}  //  SIZE {:.8}  //  SIDE {}",
            fill.price, fill.size, fill.side
        )),
        Line::from(format!(
            "FEE {} ({})  //  CLOSED PNL {}",
            money(fill.fee_usd),
            realized_fee_rate(fill),
            money(fill.closed_pnl_usd)
        )),
        Line::from(format!(
            "EXPECTED {}  //  SLIPPAGE {}",
            fill.expected_price
                .map_or_else(|| "N/A".into(), |value| format!("{value:.8}")),
            optional_bps(fill.slippage_bps)
        )),
        Line::from(format!(
            "ACK {}  //  MARKOUT {} @ {}",
            fill.acknowledgement_latency_ms
                .map_or_else(|| "N/A".into(), |value| format!("{value}ms")),
            optional_bps(fill.markout_bps),
            fill.markout_horizon_ms
                .map_or_else(|| "N/A".into(), |value| format!("{value}ms"))
        )),
        Line::from(format!(
            "EXIT CONTROLLER {}  //  EXIT REASON {}",
            fill.exit_controller_id.as_deref().unwrap_or("N/A"),
            fill.exit_reason.as_deref().unwrap_or("N/A"),
        )),
    ]
}

fn fill_scope(fill: &CohortFill, app: &App) -> &'static str {
    if app
        .backend
        .run_id
        .as_deref()
        .is_some_and(|run_id| fill.origin_run_id.as_deref() == Some(run_id))
    {
        "CURRENT"
    } else {
        "HISTORY"
    }
}

fn lifecycle_detail_lines(fill: &CohortFill) -> Vec<Line<'static>> {
    let Some(entry_price) = fill.entry_price else {
        return vec![Line::from("LIFECYCLE OPEN OR NOT RECORDED")];
    };
    let entry_time = fill
        .entry_venue_timestamp_ms
        .map_or_else(|| "NOT RECORDED".into(), fill_time);
    vec![
        Line::from(format!("ENTRY {entry_price:.8} @ {entry_time}")),
        Line::from(format!(
            "NET PNL {}  //  LIFECYCLE FEES {}  //  FUNDING {}",
            fill.net_pnl_usd
                .map_or_else(|| "N/A".into(), signed_dollars),
            fill.lifecycle_fees_usd.map_or_else(|| "N/A".into(), money),
            fill.lifecycle_funding_usd
                .map_or_else(|| "N/A".into(), signed_dollars),
        )),
        Line::from(format!(
            "HOLD {}",
            fill.holding_time_ms
                .map_or_else(|| "N/A".into(), |value| format!("{value}ms"))
        )),
    ]
}

fn signed_dollars(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn realized_fee_rate(fill: &CohortFill) -> String {
    let notional = fill.price * fill.size;
    if !notional.is_finite() || notional <= 0.0 || !fill.fee_usd.is_finite() {
        return "N/A".into();
    }
    format!("{:.2}bps", fill.fee_usd.abs() / notional * 10_000.0)
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let rows = Layout::vertical([
        Constraint::Percentage((100 - percent_y) / 2),
        Constraint::Percentage(percent_y),
        Constraint::Percentage((100 - percent_y) / 2),
    ])
    .split(area);
    Layout::horizontal([
        Constraint::Percentage((100 - percent_x) / 2),
        Constraint::Percentage(percent_x),
        Constraint::Percentage((100 - percent_x) / 2),
    ])
    .split(rows[1])[1]
}
