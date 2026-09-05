//! Selectable closed-lifecycle journal with entry-to-exit economics and regimes.

use ratatui::{
    Frame,
    layout::{Constraint, Flex, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Cell, Clear, Paragraph, Row, Table, TableState, Wrap},
};

use crate::app::App;
use crate::backend_cohort_trade_reflections::{
    CohortTradeEntryFollowthroughPath, CohortTradeReflection, CohortTradeRegimeContext,
};
use crate::cohort_format::{fill_date_time, fill_time, number, percent, signed_money};
use crate::cohort_router_format::human_token;
use crate::cohort_trade_capture::hold_capture_line;
use crate::cohort_trade_ignored_exit::lines as ignored_exit_lines;
use crate::cohort_trade_selection::CohortTradeFocus;
use crate::cohort_widgets::{panel, provider_alias, render_empty};

const HIP3_SYMBOL_COLUMN_WIDTH: u16 = 12;

/// Render newest-first authoritative closed trade history.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let trades = app.backend.cohort_checkpoint.user_trade_reflections();
    if trades.is_empty() {
        let message = crate::cohort_trade_performance::empty_epoch_history_message(app)
            .unwrap_or_else(|| "No completed backend lifecycle is available".into());
        render_empty(
            frame,
            app,
            area,
            " COMPLETED TRADES // CLOSED LIFECYCLE JOURNAL ",
            &message,
        );
        return;
    }
    let wide = area.width >= 145;
    let rows = trades
        .iter()
        .rev()
        .map(|trade| {
            if wide {
                wide_trade_row(trade, app)
            } else {
                trade_row(trade, app)
            }
        })
        .collect::<Vec<_>>();
    let current_run = trades
        .iter()
        .filter(|trade| trade_scope(trade, app) == "RUN")
        .count();
    let current_profile = trades
        .iter()
        .filter(|trade| trade_scope(trade, app) == "PROFILE")
        .count();
    let history = trades.len().saturating_sub(current_run + current_profile);
    let focus = app.effective_cohort_trade_focus() == CohortTradeFocus::Lifecycles;
    let title = format!(
        " COMPLETED TRADES // RUN {current_run} // PROFILE PRIOR {current_profile} // HISTORY {history} // ARCHIVE {} // {} // [←/→] FOCUS [↑/↓] SELECT ",
        trades.len(),
        if focus { "ACTIVE" } else { "VIEW" },
    );
    let widths = if wide {
        vec![
            Constraint::Length(7),
            Constraint::Length(16),
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(5),
            Constraint::Length(15),
            Constraint::Length(11),
            Constraint::Length(11),
            Constraint::Length(9),
            Constraint::Length(10),
            Constraint::Length(8),
            Constraint::Length(9),
            Constraint::Min(18),
        ]
    } else {
        vec![
            Constraint::Length(8),
            Constraint::Length(16),
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(6),
            Constraint::Length(15),
            Constraint::Length(9),
            Constraint::Length(9),
            Constraint::Min(12),
        ]
    };
    let headers = if wide {
        vec![
            "SCOPE",
            "EXIT DATE ET",
            "COIN",
            "SIDE",
            "STRATEGY",
            "ENTRY PX",
            "EXIT PX",
            "NET USD",
            "NET/MARGIN",
            "FEES",
            "FUNDING",
            "EXIT",
        ]
    } else {
        vec![
            "SCOPE",
            "EXIT DATE ET",
            "COIN",
            "SIDE",
            "STRATEGY",
            "NET USD",
            "RETURN",
            "EXIT",
        ]
    };
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(Row::new(headers).style(app.theme.header))
        .row_highlight_style(app.theme.highlight)
        .highlight_symbol("▸ ")
        .block(panel(title.as_str(), app));
    let selected = app
        .selected_cohort_lifecycle_index
        .min(trades.len().saturating_sub(1));
    let mut state = TableState::default().with_selected(focus.then_some(selected));
    frame.render_stateful_widget(table, area, &mut state);
}

fn trade_row<'a>(trade: &'a CohortTradeReflection, app: &App) -> Row<'a> {
    let style = pnl_style(trade.net_pnl_usd, app);
    Row::new(vec![
        Cell::from(trade_scope(trade, app)),
        Cell::from(
            trade
                .exit_venue_timestamp_ms
                .map_or_else(|| "N/A".into(), fill_date_time),
        ),
        Cell::from(trade.symbol.as_str()).style(app.theme.title),
        Cell::from(trade.side.to_uppercase()).style(side_style(&trade.side, app)),
        Cell::from(provider_alias(&trade.strategy_id)),
        Cell::from(format!("${}", signed_money(trade.net_pnl_usd))).style(style),
        Cell::from(percent(trade.net_return_on_margin_pct)).style(style),
        Cell::from(
            trade
                .exit_reason
                .as_deref()
                .map_or_else(|| "N/A".into(), human_token),
        ),
    ])
}

fn wide_trade_row<'a>(trade: &'a CohortTradeReflection, app: &App) -> Row<'a> {
    let style = pnl_style(trade.net_pnl_usd, app);
    Row::new(vec![
        Cell::from(trade_scope(trade, app)),
        Cell::from(
            trade
                .exit_venue_timestamp_ms
                .map_or_else(|| "N/A".into(), fill_date_time),
        ),
        Cell::from(trade.symbol.as_str()).style(app.theme.title),
        Cell::from(trade.side.to_uppercase()).style(side_style(&trade.side, app)),
        Cell::from(provider_alias(&trade.strategy_id)),
        Cell::from(number(trade.entry_price)),
        Cell::from(number(trade.exit_price)),
        Cell::from(format!("${}", signed_money(trade.net_pnl_usd))).style(style),
        Cell::from(percent(trade.net_return_on_margin_pct)).style(style),
        Cell::from(optional_money(trade.fees_usd)),
        Cell::from(optional_signed_money(trade.funding_usd)),
        Cell::from(
            trade
                .exit_reason
                .as_deref()
                .map_or_else(|| "N/A".into(), human_token),
        ),
    ])
}

/// Render full execution, cost, holding, and regime evidence for one lifecycle.
pub(crate) fn render_detail(frame: &mut Frame, app: &App, area: Rect) {
    let trades = app.backend.cohort_checkpoint.user_trade_reflections();
    let display_index = app
        .selected_cohort_lifecycle_index
        .min(trades.len().saturating_sub(1));
    let Some(index) = trades.len().checked_sub(display_index + 1) else {
        return;
    };
    let Some(trade) = trades.get(index) else {
        return;
    };
    let modal = centered_rect(88, 84, area);
    frame.render_widget(Clear, modal);
    frame.render_widget(
        Paragraph::new(detail_lines(trade, app))
            .wrap(Wrap { trim: true })
            .block(panel(" CLOSED TRADE INSPECTOR // BACKEND JOURNAL ", app)),
        modal,
    );
}

fn detail_lines<'a>(trade: &'a CohortTradeReflection, app: &App) -> Vec<Line<'a>> {
    let mut lines = vec![
        identity_line(trade, app),
        scope_line(trade, app),
        Line::from(format!("LIFECYCLE {}", trade.lifecycle_id)),
        Line::from(format!("ORIGIN RUN {}", trade.source_run_id)),
        Line::from(format!(
            "ENTRY OWNER {}  //  EXIT CONTROLLER {}  //  CROSS-PROVIDER {}",
            provider_alias(&trade.strategy_id),
            provider_alias(&trade.exit_controller_strategy_id),
            if trade.cross_provider_exit {
                "YES"
            } else {
                "NO"
            },
        )),
        Line::from(""),
        execution_line("ENTRY", trade.entry_price, trade.entry_venue_timestamp_ms),
        execution_line("EXIT ", trade.exit_price, trade.exit_venue_timestamp_ms),
        Line::from(format!(
            "MARGIN {}  //  LEVERAGE {}  //  HOLD {}",
            optional_money(trade.entry_margin_used_usd),
            trade
                .leverage
                .map_or_else(|| "N/A".into(), |value| format!("{value:.1}x")),
            holding_time(trade.holding_time_ms),
        )),
        economics_line(trade, app),
        Line::from(format!(
            "FEES {}  //  FUNDING {}  //  EXIT {}",
            optional_money(trade.fees_usd),
            optional_signed_money(trade.funding_usd),
            trade
                .exit_reason
                .as_deref()
                .map_or_else(|| "N/A".into(), human_token),
        )),
        Line::from(""),
        regime_line("ENTRY SIGNAL", &trade.entry_signal),
        regime_line("ENTRY CANON ", &trade.entry_canonical),
        assessment_line(
            "ENTRY ASSESS",
            trade.entry_structure_support_score,
            &trade.entry_structure_stance,
            trade.entry_component_alignment_score,
            &trade.entry_component_stance,
            trade.entry_movement_strength,
        ),
        Line::from(format!(
            "ENTRY TIMER {}",
            human_token(&trade.entry_maximum_hold_context),
        )),
        regime_line("EXIT SIGNAL ", &trade.exit_signal),
        regime_line("EXIT CANON  ", &trade.exit_canonical),
        Line::from(format!(
            "EXIT STRUCT {}  //  TIMER CONTEXT {}",
            human_token(&trade.exit_structure_stance),
            human_token(&trade.exit_maximum_hold_context),
        )),
    ];
    if let Some(opposition) = &trade.regime_opposition {
        lines.push(Line::from(format!(
            "OPPOSITION {}/{} DECISIONS  //  MAX RUN {}  //  AT EXIT {}",
            opposition.opposed_decisions,
            opposition.completed_decisions,
            opposition.maximum_consecutive_opposed,
            if opposition.current_active {
                "ACTIVE"
            } else {
                "CLEAR"
            },
        )));
    }
    if let Some(outcome) = &trade.ignored_provider_exit_outcome {
        lines.push(Line::from(""));
        lines.extend(ignored_exit_lines(outcome, app));
    }
    lines.extend(hold_capture_line(trade, app));
    lines.extend(entry_followthrough_lines(trade));
    lines.extend(path_lines(trade));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "[Enter/Esc] CLOSE // VALUES ARE BACKEND JOURNAL EVIDENCE",
        app.theme.muted,
    )));
    lines
}

fn trade_scope(trade: &CohortTradeReflection, app: &App) -> &'static str {
    if app.backend.run_id.as_deref() == Some(trade.source_run_id.as_str()) {
        return "RUN";
    }
    let current = app
        .backend
        .cohort_checkpoint
        .trade_performance
        .as_ref()
        .and_then(|performance| performance.current_profile.as_ref());
    match current {
        Some(profile)
            if trade.source_profile_fingerprint.as_deref()
                == Some(profile.profile_fingerprint.as_str()) =>
        {
            "PROFILE"
        }
        Some(_) if trade.source_profile_fingerprint.is_some() => "HISTORY",
        Some(_) => "UNSCOPED",
        None => "COMPAT",
    }
}

fn scope_line(trade: &CohortTradeReflection, app: &App) -> Line<'static> {
    let fingerprint = trade.source_profile_fingerprint.as_deref().map_or_else(
        || "NOT RECORDED".into(),
        |value| value.chars().take(12).collect::<String>(),
    );
    Line::from(format!(
        "SCOPE {}  //  PROFILE {}",
        trade_scope(trade, app),
        fingerprint,
    ))
}

fn entry_followthrough_lines(trade: &CohortTradeReflection) -> Vec<Line<'static>> {
    [240_u16, 2_880]
        .into_iter()
        .filter_map(|horizon| {
            trade
                .entry_followthrough_paths
                .get(&horizon)
                .map(|path| entry_followthrough_line(horizon, path))
        })
        .collect()
}

fn entry_followthrough_line(
    horizon: u16,
    path: &CohortTradeEntryFollowthroughPath,
) -> Line<'static> {
    let label = if horizon.is_multiple_of(60) {
        format!("{}H", horizon / 60)
    } else {
        format!("{horizon}M")
    };
    let return_bps = path
        .directional_close_return_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.2}bps"));
    let stop = match path.protective_stop_price_crossed {
        Some(true) => "STOP PX CROSSED",
        Some(false) if path.status.eq_ignore_ascii_case("resolved") => "STOP PX CLEAR",
        Some(false) => "STOP PX CLEAR SO FAR",
        None => "STOP N/A",
    };
    Line::from(format!(
        "POST-ENTRY {label}  {}  {}/{}  RETURN {return_bps}  {stop}",
        path.status.to_uppercase(),
        path.bars_observed,
        path.bars_required,
    ))
}

fn assessment_line(
    label: &str,
    structure_score: Option<f64>,
    structure_stance: &str,
    component_score: Option<f64>,
    component_stance: &str,
    movement_strength: Option<f64>,
) -> Line<'static> {
    Line::from(format!(
        "{label}  STRUCT {} {}  //  COMP {} {}  //  STRENGTH {}",
        optional_score(structure_score),
        human_token(structure_stance),
        optional_score(component_score),
        human_token(component_stance),
        movement_strength.map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0)),
    ))
}

fn optional_score(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |score| format!("{score:+.2}"))
}

fn identity_line<'a>(trade: &'a CohortTradeReflection, app: &App) -> Line<'a> {
    Line::from(vec![
        Span::styled(
            format!("{} {}", trade.symbol, trade.side.to_uppercase()),
            side_style(&trade.side, app),
        ),
        Span::raw(format!("  //  {}", provider_alias(&trade.strategy_id))),
    ])
}

fn execution_line(label: &str, price: Option<f64>, timestamp_ms: Option<u64>) -> Line<'static> {
    Line::from(format!(
        "{label} {}  @  {}",
        price.map_or_else(|| "N/A".into(), |value| format!("${value:.8}")),
        timestamp_ms.map_or_else(|| "N/A".into(), fill_time),
    ))
}

fn economics_line<'a>(trade: &CohortTradeReflection, app: &App) -> Line<'a> {
    let style = pnl_style(trade.net_pnl_usd, app);
    Line::from(vec![
        Span::raw("PRICE MOVE "),
        Span::styled(percent(trade.price_return_pct), style),
        Span::raw("  //  NET/MARGIN "),
        Span::styled(percent(trade.net_return_on_margin_pct), style),
        Span::raw("  //  NET "),
        Span::styled(format!("${}", signed_money(trade.net_pnl_usd)), style),
    ])
}

fn regime_line(label: &str, value: &CohortTradeRegimeContext) -> Line<'static> {
    Line::from(format!(
        "{label}  1M {}  5M {}  15M {}  CALL {}  CONF {}",
        optional_token(value.state_1m.as_deref()),
        optional_token(value.state_5m.as_deref()),
        optional_token(value.context_15m.as_deref()),
        optional_token(value.primary_regime.as_deref()),
        percent(value.confidence.map(|score| score * 100.0)),
    ))
}

fn path_lines(trade: &CohortTradeReflection) -> Vec<Line<'static>> {
    [5_u16, 60]
        .into_iter()
        .filter_map(|horizon| {
            trade.post_exit_paths.get(&horizon).map(|path| {
                Line::from(format!(
                    "POST-EXIT {horizon}M  {}  RETURN {}  {}",
                    path.status.to_uppercase(),
                    path.directional_close_return_bps
                        .map_or_else(|| "N/A".into(), |value| format!("{value:+.2}bps")),
                    path.interpretation
                        .as_deref()
                        .map_or_else(|| "N/A".into(), human_token),
                ))
            })
        })
        .collect()
}

fn optional_token(value: Option<&str>) -> String {
    value.map_or_else(|| "N/A".into(), |text| text.to_uppercase())
}

fn optional_money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.2}"))
}

fn optional_signed_money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:+.4}"))
}

fn holding_time(value: Option<u64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |milliseconds| {
            let minutes = milliseconds / 60_000;
            format!("{}h {:02}m", minutes / 60, minutes % 60)
        },
    )
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

fn side_style(side: &str, app: &App) -> Style {
    if side == "long" {
        app.theme.bull
    } else {
        app.theme.bear
    }
}

fn centered_rect(horizontal: u16, vertical: u16, area: Rect) -> Rect {
    let [vertical] = Layout::vertical([Constraint::Percentage(vertical)])
        .flex(Flex::Center)
        .areas(area);
    let [centered] = Layout::horizontal([Constraint::Percentage(horizontal)])
        .flex(Flex::Center)
        .areas(vertical);
    centered
}

#[cfg(test)]
#[path = "cohort_trade_history_tests.rs"]
mod tests;
