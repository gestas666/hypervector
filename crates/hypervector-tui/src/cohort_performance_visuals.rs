//! Source-backed performance visualizations for the cohort dashboard.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort::CohortFill;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;
use crate::backend_cohort_trade_reflections::CohortTradeReflection;
use crate::cohort_equity_curve::ClosedEquityCurve;
use crate::cohort_equity_summary::{ClosedEquitySummary, closed_path_maximum_drawdown_pct};
use crate::cohort_format::{money, percent, signed_money};
use crate::cohort_widgets::{panel, render_empty};

#[derive(Debug, Clone, Default, PartialEq)]
struct OutcomeSummary {
    trades: usize,
    wins: usize,
    losses: usize,
    net_pnl_usd: f64,
}

#[derive(Debug, Clone, Default, PartialEq)]
struct FillQuality {
    measured: usize,
    total_fees_usd: f64,
    mean_slippage_bps: Option<f64>,
    mean_ack_ms: Option<f64>,
    mean_markout_bps: Option<f64>,
}

struct EquityPath<'a> {
    start: Option<f64>,
    baseline: Option<f64>,
    total: f64,
    values: Vec<f64>,
    deltas: Vec<f64>,
    trades: Vec<&'a CohortTradeReflection>,
}

fn summarize_direction<'a>(
    trades: impl Iterator<Item = &'a CohortTradeReflection>,
    side: &str,
) -> OutcomeSummary {
    let selected = trades.filter(|trade| trade.side == side);
    selected.fold(OutcomeSummary::default(), |mut summary, trade| {
        summary.trades += 1;
        summary.wins += usize::from(trade.net_pnl_usd > 0.0);
        summary.losses += usize::from(trade.net_pnl_usd < 0.0);
        summary.net_pnl_usd += trade.net_pnl_usd;
        summary
    })
}

fn summarize_fills(fills: &[CohortFill]) -> FillQuality {
    let slippage = fills
        .iter()
        .filter_map(|fill| fill.slippage_bps)
        .collect::<Vec<_>>();
    let acknowledgement = fills
        .iter()
        .filter_map(|fill| fill.acknowledgement_latency_ms.map(|value| value as f64))
        .collect::<Vec<_>>();
    let markout = fills
        .iter()
        .filter_map(|fill| fill.markout_bps)
        .collect::<Vec<_>>();
    FillQuality {
        measured: fills.len(),
        total_fees_usd: fills.iter().map(|fill| fill.fee_usd).sum(),
        mean_slippage_bps: mean(&slippage),
        mean_ack_ms: mean(&acknowledgement),
        mean_markout_bps: mean(&markout),
    }
}

fn mean(values: &[f64]) -> Option<f64> {
    (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64)
}

/// Render cumulative PnL, directional outcomes, and measured fill friction.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    if app
        .backend
        .cohort_checkpoint
        .user_trade_reflections()
        .is_empty()
    {
        let message = crate::cohort_trade_performance::empty_epoch_history_message(app)
            .unwrap_or_else(|| "Awaiting closed backend lifecycles".into());
        render_empty(frame, app, area, " PERFORMANCE VISUALS ", &message);
        return;
    }
    let columns = Layout::horizontal([
        Constraint::Percentage(44),
        Constraint::Percentage(28),
        Constraint::Percentage(28),
    ])
    .split(area);
    render_pnl_trajectory(frame, app, columns[0]);
    render_directional_ledger(frame, app, columns[1]);
    render_execution_friction(frame, app, columns[2]);
}

fn render_pnl_trajectory(frame: &mut Frame, app: &App, area: Rect) {
    let block = panel(" CURRENT RUN EQUITY // CLOSED LINE ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let rows = Layout::vertical([
        Constraint::Length(1),
        Constraint::Length(1),
        Constraint::Min(3),
        Constraint::Length(1),
        Constraint::Length(1),
    ])
    .split(inner);
    let path = equity_path(app);
    frame.render_widget(Paragraph::new(equity_command_header(&path, app)), rows[0]);
    frame.render_widget(
        Paragraph::new(performance_summary(app, &path.values)),
        rows[1],
    );
    render_equity_plot(frame, app, rows[2], &path);
    frame.render_widget(
        Paragraph::new(trade_axis(rows[3].width, path.trades.len())),
        rows[3],
    );
    frame.render_widget(Paragraph::new(outcome_tape(app, &path.trades)), rows[4]);
}

fn equity_path(app: &App) -> EquityPath<'_> {
    let trades = current_run_trades(app);
    let trajectory = cumulative_run_pnl(&trades);
    let reported = current_run_performance(app);
    let path_valid = reported.is_some_and(|value| {
        value.closed_trades == trades.len()
            && (value.net_pnl_usd - trajectory.last().copied().unwrap_or(0.0)).abs() <= 1e-6
    });
    let start = app
        .backend
        .cohort_checkpoint
        .portfolio
        .as_ref()
        .filter(|_| path_valid)
        .map(|value| value.initial_equity_usd);
    let total = reported.map_or_else(
        || trajectory.last().copied().unwrap_or(0.0),
        |value| value.net_pnl_usd,
    );
    EquityPath {
        start,
        baseline: start,
        total,
        values: start.map_or_else(Vec::new, |baseline| {
            trajectory.iter().map(|value| baseline + value).collect()
        }),
        deltas: trades.iter().map(|trade| trade.net_pnl_usd).collect(),
        trades,
    }
}

fn render_equity_plot(frame: &mut Frame, app: &App, area: Rect, path: &EquityPath<'_>) {
    let Some(baseline) = path.baseline else {
        frame.render_widget(
            Paragraph::new("CURRENT RUN PATH UNAVAILABLE // BASELINE OR IDENTITY MISMATCH")
                .centered()
                .style(app.theme.muted),
            area,
        );
        return;
    };
    frame.render_widget(
        ClosedEquityCurve {
            values: &path.values,
            deltas: &path.deltas,
            baseline,
            gain: app.theme.bull,
            loss: app.theme.bear,
            neutral: app.theme.muted,
            baseline_style: app.theme.bar_ghost,
            drawdown: app.theme.carry,
        },
        area,
    );
}

fn equity_command_header(path: &EquityPath<'_>, app: &App) -> Line<'static> {
    let summary = ClosedEquitySummary::from_path(path.start, path.total);
    let live = app
        .backend
        .cohort_checkpoint
        .portfolio
        .as_ref()
        .map(|value| value.final_equity_usd);
    let mark_gap = live
        .zip(summary.closed_equity)
        .map(|(mark, close)| mark - close);
    let return_label = summary
        .return_pct
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.2}%"));
    Line::from(vec![
        Span::raw("LIVE "),
        Span::styled(live.map_or_else(|| "N/A".into(), money), app.theme.cyan),
        Span::raw("  CLOSED EQ "),
        Span::styled(
            summary.closed_equity.map_or_else(|| "N/A".into(), money),
            pnl_style(summary.net, app),
        ),
        Span::raw("  "),
        Span::styled(
            format!("{} / {return_label}", signed_currency(summary.net)),
            pnl_style(summary.net, app),
        ),
        Span::raw("  MARK GAP "),
        Span::styled(
            mark_gap.map_or_else(|| "N/A".into(), signed_currency),
            mark_gap.map_or(app.theme.muted, |value| pnl_style(value, app)),
        ),
    ])
}

fn performance_summary(app: &App, path: &[f64]) -> Line<'static> {
    let drawdown = closed_path_maximum_drawdown_pct(path)
        .map_or_else(|| "N/A".into(), |value| format!("{value:.2}%"));
    let Some(performance) = app.backend.cohort_checkpoint.trade_performance.as_ref() else {
        return Line::from(format!(
            "RUN TRADES N/A  W/L/BE N/A  WR N/A  PF N/A  CLOSED DD {drawdown}",
        ));
    };
    let Some(total) = current_run_performance(app) else {
        let history = all_time_performance(app, performance);
        return Line::from(format!(
            "RUN IDENTITY MISMATCH  CLOSED DD {drawdown}  HIST {}T {}",
            history.closed_trades,
            signed_currency(history.net_pnl_usd),
        ));
    };
    let win_rate = total
        .win_rate_pct
        .map_or_else(|| "N/A".into(), |number| format!("{number:.1}%"));
    let profit_factor = profit_factor_label(total);
    let history_value = all_time_performance(app, performance);
    let history = format!(
        "  HIST {}T {}",
        history_value.closed_trades,
        signed_currency(history_value.net_pnl_usd)
    );
    Line::from(format!(
        "RUN {}T  W{} L{} BE{}  WR {win_rate}  PF {profit_factor}  CLOSED DD {drawdown}{history}",
        total.closed_trades, total.wins, total.losses, total.breakeven
    ))
}

fn all_time_performance<'a>(
    app: &'a App,
    performance: &'a crate::backend_cohort_trade_performance::CohortTradePerformance,
) -> &'a crate::backend_cohort_trade_performance::CohortTradePerformanceSummary {
    app.backend
        .cohort_checkpoint
        .all_time_performance()
        .map_or(&performance.total, |history| &history.total)
}

fn outcome_tape(app: &App, trades: &[&CohortTradeReflection]) -> Line<'static> {
    let start = trades.len().saturating_sub(6);
    let mut spans = vec![Span::styled("RECENT ", app.theme.muted)];
    for (offset, trade) in trades.iter().skip(start).enumerate() {
        let marker = if trade.net_pnl_usd > 0.0 {
            "▲"
        } else if trade.net_pnl_usd < 0.0 {
            "▼"
        } else {
            "◆"
        };
        let label = format!(
            "[{:02} {} {marker} {}] ",
            start + offset + 1,
            trade.symbol,
            signed_currency(trade.net_pnl_usd)
        );
        spans.push(Span::styled(label, pnl_style(trade.net_pnl_usd, app)));
    }
    Line::from(spans)
}

fn trade_axis(width: u16, trades: usize) -> Line<'static> {
    const AXIS_WIDTH: usize = 11;
    let left = "TRADE 0";
    let right = format!("TRADE {trades}");
    let available = usize::from(width).saturating_sub(AXIS_WIDTH);
    let gap = available.saturating_sub(left.len() + right.len());
    Line::from(format!("{:AXIS_WIDTH$}{left}{:gap$}{right}", "", ""))
}

fn current_run_performance(
    app: &App,
) -> Option<&crate::backend_cohort_trade_performance::CohortTradePerformanceSummary> {
    app.backend
        .cohort_checkpoint
        .trade_performance
        .as_ref()
        .and_then(|value| value.current_run.as_ref())
        .filter(|run| app.backend.run_id.as_deref() == Some(run.run_id.as_str()))
        .map(|run| &run.total)
}

fn signed_currency(value: f64) -> String {
    if value < 0.0 {
        format!("-${:.2}", value.abs())
    } else {
        format!("+${value:.2}")
    }
}

fn render_directional_ledger(frame: &mut Frame, app: &App, area: Rect) {
    let trades = current_run_trades(app);
    let long = summarize_direction(trades.iter().copied(), "long");
    let short = summarize_direction(trades.iter().copied(), "short");
    let lines = vec![
        direction_line("▲ LONG", &long, app),
        direction_pnl_line(&long, app),
        Line::from(""),
        direction_line("▼ SHORT", &short, app),
        direction_pnl_line(&short, app),
        Line::from(Span::styled("CURRENT RUN ONLY", app.theme.muted)),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" CURRENT RUN // LONG-SHORT ", app)),
        area,
    );
}

fn direction_line<'a>(label: &'a str, value: &OutcomeSummary, app: &App) -> Line<'a> {
    let rate = (value.trades > 0).then(|| value.wins as f64 / value.trades as f64 * 100.0);
    Line::from(vec![
        Span::styled(format!("{label:<8}"), pnl_style(value.net_pnl_usd, app)),
        Span::raw(format!(
            " {}T  W{}-L{}  ",
            value.trades, value.wins, value.losses
        )),
        Span::styled(percent(rate), app.theme.gold),
    ])
}

fn direction_pnl_line<'a>(value: &OutcomeSummary, app: &App) -> Line<'a> {
    Line::from(vec![
        Span::raw("         NET "),
        Span::styled(
            format!("${}", signed_money(value.net_pnl_usd)),
            pnl_style(value.net_pnl_usd, app),
        ),
    ])
}

fn render_execution_friction(frame: &mut Frame, app: &App, area: Rect) {
    let fills = if app.backend.cohort_checkpoint.fill_details.is_empty() {
        &app.backend.cohort.fills
    } else {
        &app.backend.cohort_checkpoint.fill_details
    };
    let quality = summarize_fills(fills);
    let closed_funding = current_run_performance(app).map(|value| value.funding_usd);
    let lines = vec![
        Line::from(format!("CURRENT RUN FILL LEGS {}", quality.measured)),
        friction_line("SLIPPAGE", quality.mean_slippage_bps, "bps", app),
        friction_line("ACK", quality.mean_ack_ms, "ms", app),
        friction_line("MARKOUT", quality.mean_markout_bps, "bps", app),
        Line::from(format!(
            "FILL FEES {}  CLOSED FUND {}",
            money(quality.total_fees_usd),
            closed_funding.map_or_else(
                || "N/A".into(),
                |value| { format!("${}", signed_money(value)) }
            ),
        )),
        Line::from(Span::styled(
            "VENUE FILL LEGS // NO ESTIMATES",
            app.theme.muted,
        )),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" EXECUTION FRICTION // CURRENT RUN ", app)),
        area,
    );
}

fn profit_factor_label(value: &CohortTradePerformanceSummary) -> String {
    if value.closed_trades == 0 {
        return "N/A".into();
    }
    value
        .profit_factor
        .map_or_else(|| "∞".into(), |number| format!("{number:.2}"))
}

fn friction_line<'a>(label: &'a str, value: Option<f64>, unit: &'a str, app: &App) -> Line<'a> {
    let rendered = value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2} {unit}"));
    Line::from(vec![
        Span::raw(format!("{label:<10}")),
        Span::styled(rendered, value.map_or(app.theme.muted, |_| app.theme.cyan)),
    ])
}

fn cumulative_run_pnl(trades: &[&CohortTradeReflection]) -> Vec<f64> {
    let mut cumulative = vec![0.0];
    for trade in trades {
        cumulative.push(cumulative.last().copied().unwrap_or(0.0) + trade.net_pnl_usd);
    }
    cumulative
}

fn current_run_trades(app: &App) -> Vec<&CohortTradeReflection> {
    let ordered = chronological(app.backend.cohort_checkpoint.user_trade_reflections());
    let Some(run_id) = app.backend.run_id.as_deref() else {
        return Vec::new();
    };
    ordered
        .into_iter()
        .filter(|trade| trade.source_run_id == run_id)
        .collect()
}

fn chronological(trades: &[CohortTradeReflection]) -> Vec<&CohortTradeReflection> {
    let mut ordered = trades.iter().collect::<Vec<_>>();
    ordered.sort_by_key(|trade| trade.exit_venue_timestamp_ms.unwrap_or(0));
    ordered
}

fn pnl_style(value: f64, app: &App) -> ratatui::style::Style {
    if value > 0.0 {
        app.theme.bull
    } else if value < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

#[cfg(test)]
#[path = "cohort_performance_visuals_tests.rs"]
mod tests;
