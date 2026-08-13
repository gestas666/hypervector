//! Regime transition and paper-trade journal tables.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    style::Style,
    text::Span,
    widgets::{Block, Borders, Row, Table},
};

use super::{dashboard::normalized_zero, time::format_timestamp_display};
use crate::{
    app::App,
    model::{PaperTradeRecord, RegimeEvent, RegimeState},
};

pub(super) fn render_event_log(f: &mut Frame, app: &App, area: Rect) {
    let max_rows = area.height.saturating_sub(3).max(5) as usize;
    let current_ts = &app.current_snapshot().timestamp_str;
    let events = app
        .events
        .iter()
        .filter(|event| &event.timestamp_str <= current_ts)
        .rev()
        .take(max_rows)
        .collect::<Vec<_>>();
    let rows = event_rows(app, &events);
    let selected = if events.is_empty() {
        0
    } else {
        app.selected_event_index.min(events.len() - 1) + 1
    };
    let table = Table::new(rows, event_constraints())
        .header(event_header(app))
        .block(
            Block::default()
                .title(format!(
                    " RECENT REGIME TRANSITION AUDIT LOG (Use [↑/↓] or [j/k] to navigate, [Enter] for details) [{selected}/{}] ",
                    events.len()
                ))
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        );
    f.render_widget(table, area);
}

fn event_header(app: &App) -> Row<'static> {
    Row::new(
        [
            "Timestamp",
            "Timestamp",
            "From State",
            "To State",
            "Price",
            "Trigger Diagnostic",
        ]
        .into_iter()
        .map(|value| Span::styled(value, app.theme.header)),
    )
    .height(1)
}

fn event_constraints() -> [Constraint; 5] {
    [
        Constraint::Length(19),
        Constraint::Length(40),
        Constraint::Length(40),
        Constraint::Length(12),
        Constraint::Min(25),
    ]
}

fn event_rows(app: &App, events: &[&RegimeEvent]) -> Vec<Row<'static>> {
    if events.is_empty() {
        return vec![empty_event_row(app)];
    }
    let selected = app.selected_event_index.min(events.len() - 1);
    events
        .iter()
        .enumerate()
        .map(|(index, event)| event_row(app, event, index == selected))
        .collect()
}

fn event_row(app: &App, event: &RegimeEvent, selected: bool) -> Row<'static> {
    let row_style = if selected {
        app.theme.highlight
    } else {
        Style::default()
    };
    let to_style = if selected {
        app.theme.highlight
    } else {
        regime_style(app, event.to_state)
    };
    Row::new(vec![
        Span::styled(
            format_timestamp_display(&event.timestamp_str),
            if selected {
                app.theme.highlight
            } else {
                app.theme.muted
            },
        ),
        Span::styled(event.from_state.display_name().to_string(), row_style),
        Span::styled(event.to_state.display_name().to_string(), to_style),
        Span::styled(
            format!("${:.2}", event.price),
            if selected {
                app.theme.highlight
            } else {
                app.theme.gold
            },
        ),
        Span::styled(
            event.trigger_reason.clone(),
            if selected {
                app.theme.highlight
            } else {
                app.theme.cyan
            },
        ),
    ])
    .style(row_style)
}

fn empty_event_row(app: &App) -> Row<'static> {
    Row::new(vec![
        Span::styled("—", app.theme.muted),
        Span::styled("NO CHANGE", app.theme.muted),
        Span::styled(
            app.current_snapshot().state.primary_label(),
            app.theme.title,
        ),
        Span::styled(
            format!("${:.2}", app.current_snapshot().price),
            app.theme.gold,
        ),
        Span::styled(
            "No regime transition observed in this backend run",
            app.theme.cyan,
        ),
    ])
}

fn regime_style(app: &App, state: RegimeState) -> Style {
    match state {
        RegimeState::BullMomentum => app.theme.bull,
        RegimeState::BearMomentum => app.theme.bear,
        RegimeState::VolatilityCoiling => app.theme.coiling,
        RegimeState::FundingCarry => app.theme.carry,
        RegimeState::RangeChop | RegimeState::Unknown => app.theme.chop,
    }
}

pub(super) fn render_paper_journal_log(f: &mut Frame, app: &App, area: Rect) {
    let max_rows = area.height.saturating_sub(3).max(1) as usize;
    let open_count = usize::from(app.active_position.is_active());
    let closed_limit = max_rows.saturating_sub(open_count);
    let selected = app
        .selected_trade_index
        .min(app.paper_trades.len().saturating_sub(1));
    let window_start = selected.saturating_sub(closed_limit.saturating_sub(1));
    let rows = journal_rows(app, closed_limit, selected, window_start);
    let table = Table::new(rows, journal_constraints())
        .header(journal_header(app))
        .block(journal_block(app, open_count));
    f.render_widget(table, area);
}

fn journal_rows(
    app: &App,
    closed_limit: usize,
    selected: usize,
    window_start: usize,
) -> Vec<Row<'static>> {
    let mut rows = Vec::with_capacity(closed_limit + 1);
    if app.active_position.is_active() {
        rows.push(open_position_row(app));
    }
    rows.extend(
        app.paper_trades
            .iter()
            .rev()
            .skip(window_start)
            .take(closed_limit)
            .enumerate()
            .map(|(index, trade)| closed_trade_row(app, trade, window_start + index == selected)),
    );
    rows
}

fn open_position_row(app: &App) -> Row<'static> {
    let position = &app.active_position;
    let direction_style = if position.direction == "LONG" {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let pnl_style = if app.paper_stats.unrealized_pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    Row::new(vec![
        Span::styled("OPEN", app.theme.gold),
        Span::styled(
            format_timestamp_display(&position.entry_timestamp),
            app.theme.muted,
        ),
        Span::styled(position.direction.clone(), direction_style),
        Span::styled(format!("${:.2}", position.entry_price), app.theme.title),
        Span::styled("OPEN", app.theme.cyan),
        Span::styled(format!("{:.4}", position.size_btc), app.theme.cyan),
        Span::styled(format!("{:.1}x", position.leverage), app.theme.gold),
        Span::styled(
            format!(
                "UNREAL {:+.2}",
                normalized_zero(app.paper_stats.unrealized_pnl)
            ),
            pnl_style,
        ),
        Span::styled(open_exit_status(app), app.theme.gold),
    ])
}

fn closed_trade_row(app: &App, trade: &PaperTradeRecord, selected: bool) -> Row<'static> {
    let direction_style = if trade.direction == "LONG" {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let (sign, pnl_style) = if trade.pnl_usd >= 0.0 {
        ("+", app.theme.bull)
    } else {
        ("", app.theme.bear)
    };
    let row = Row::new(vec![
        Span::styled(trade.trade_id.clone(), app.theme.gold),
        Span::styled(
            format_timestamp_display(&trade.timestamp_str),
            app.theme.muted,
        ),
        Span::styled(trade.direction.clone(), direction_style),
        Span::styled(format!("${:.2}", trade.entry_price), app.theme.title),
        Span::styled(format!("${:.2}", trade.exit_price), app.theme.title),
        Span::styled(format!("{:.4}", trade.size_btc), app.theme.cyan),
        Span::styled(format!("{:.1}x", trade.leverage), app.theme.gold),
        Span::styled(
            format!("{sign}{:.2} ({sign}{:.2}%)", trade.pnl_usd, trade.pnl_pct),
            pnl_style,
        ),
        Span::styled(trade.exit_reason.clone(), app.theme.muted),
    ]);
    if selected {
        row.style(app.theme.highlight)
    } else {
        row
    }
}

fn journal_header(app: &App) -> Row<'static> {
    Row::new(
        [
            "Trade ID".to_string(),
            "Timestamp".to_string(),
            "Direction".to_string(),
            "Entry Price".to_string(),
            "Exit Price".to_string(),
            format!("Size ({})", app.symbol),
            "Leverage".to_string(),
            "Realized PnL".to_string(),
            "Exit Trigger".to_string(),
        ]
        .into_iter()
        .map(|value| Span::styled(value, app.theme.header)),
    )
    .height(1)
}

fn journal_constraints() -> [Constraint; 9] {
    [
        Constraint::Length(12),
        Constraint::Length(24),
        Constraint::Length(9),
        Constraint::Length(13),
        Constraint::Length(13),
        Constraint::Length(12),
        Constraint::Length(9),
        Constraint::Length(22),
        Constraint::Min(16),
    ]
}

fn journal_block<'a>(app: &App, open_count: usize) -> Block<'a> {
    let selected = usize::from(!app.paper_trades.is_empty())
        + app
            .selected_trade_index
            .min(app.paper_trades.len().saturating_sub(1));
    Block::default()
        .title(format!(
            " {} (CLOSED TRADES: {} | OPEN POSITIONS: {open_count} | SELECTED: {selected}/{}) ",
            journal_title(app),
            app.paper_trades.len(),
            app.paper_trades.len()
        ))
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border)
}

fn journal_title(app: &App) -> &'static str {
    if app.backend.execution_mode.as_deref() == Some("live") && app.backend.live_armed == Some(true)
    {
        "LIVE EXECUTION JOURNAL"
    } else {
        "LIVE PAPER JOURNAL"
    }
}

fn open_exit_status(app: &App) -> &'static str {
    let configured = app
        .backend
        .strategy_params
        .get("target_margin_pct")
        .and_then(serde_json::Value::as_f64)
        .or_else(|| {
            app.backend
                .exits
                .get("target_margin_pct")
                .and_then(serde_json::Value::as_f64)
        });
    let hypervelocity = app
        .backend
        .strategy_name
        .as_deref()
        .is_some_and(|name| name.starts_with("hypervelocity"));
    if !app.backend.active_target_prices.is_empty() || configured.is_some() || hypervelocity {
        "AWAITING TP"
    } else {
        "AWAITING STRATEGY EXIT"
    }
}
