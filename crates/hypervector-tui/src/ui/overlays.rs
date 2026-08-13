//! Footer controls and read-only event, trade, and help overlays.

use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Clear, Paragraph},
};

use super::time::format_timestamp_display;
use crate::{
    app::App,
    model::{PaperTradeRecord, RegimeEvent},
};

pub(super) fn render_requested_overlays(f: &mut Frame, app: &App) {
    let area = f.area();
    if app.show_event_detail_modal {
        render_event_modal(f, app, area);
    }
    if app.show_trade_detail_modal {
        render_trade_modal(f, app, area);
    }
    if app.show_help_overlay {
        render_help_overlay(f, app, area);
    }
}

pub(super) fn render_footer(f: &mut Frame, app: &App, area: Rect) {
    let line = if app.active_tab == 3 {
        config_footer(app)
    } else if app.backend.is_apex_mm() {
        apex_footer(app)
    } else {
        standard_footer(app)
    };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(
        Paragraph::new(line)
            .block(block)
            .alignment(Alignment::Center),
        area,
    );
}

fn config_footer(app: &App) -> Line<'static> {
    let rows = crate::config_view::backend_config_rows(&app.backend);
    let selected = if rows.is_empty() {
        0
    } else {
        app.config.selected_option_index.min(rows.len() - 1) + 1
    };
    Line::from(vec![
        Span::styled("[Tab / 1-4]", app.theme.gold),
        Span::raw(" Switch Screen │ "),
        Span::styled("[↑/↓ j/k]", app.theme.gold),
        Span::raw(" Select Option │ "),
        Span::styled("[q]", app.theme.gold),
        Span::raw(" Quit │ "),
        Span::styled(format!("Option {selected}/{}", rows.len()), app.theme.cyan),
        Span::raw(" │ BACKEND READ ONLY"),
    ])
}

fn apex_footer(app: &App) -> Line<'static> {
    Line::from(vec![
        Span::styled("[Tab / 1-4]", app.theme.gold),
        Span::raw(" Switch Screen | "),
        Span::styled("[Space]", app.theme.gold),
        Span::raw(" Play/Pause | "),
        Span::styled("[Left/Right]", app.theme.gold),
        Span::raw(" Scrub L2 History | "),
        Span::styled(
            format!("MM EVENTS {}", app.backend.apex_mm.recent_events.len()),
            app.theme.cyan,
        ),
        Span::raw(" | "),
        Span::styled("[?]", app.theme.gold),
        Span::raw(" Help | BACKEND READ ONLY"),
    ])
}

fn standard_footer(app: &App) -> Line<'static> {
    let total = app.snapshots.len();
    let current = app.current_index + 1;
    let percent = (current as f64 / total as f64 * 100.0).clamp(0.0, 100.0);
    let filled = (percent / 100.0 * 16.0) as usize;
    let selection = match app.active_tab {
        0 => " Select Trade | ",
        1 => " Select Event | ",
        2 => " Chart Playhead | ",
        _ => " Select Option | ",
    };
    Line::from(vec![
        Span::styled("[Tab / 1-4]", app.theme.gold),
        Span::raw(" Switch Screen View │ "),
        Span::styled("[Space]", app.theme.gold),
        Span::raw(" Play/Pause │ "),
        Span::styled("[←/→]", app.theme.gold),
        Span::raw(" Scrub │ "),
        Span::styled("[↑/↓ j/k]", app.theme.gold),
        Span::raw(selection),
        Span::styled("[Enter]", app.theme.gold),
        Span::raw(" Details │ "),
        Span::styled("[?]", app.theme.gold),
        Span::raw(" Help │ "),
        Span::styled("Scrub: ", app.theme.cyan),
        Span::styled(
            format!(
                "[{}{}] {percent:.1}% ({current}/{total})",
                "█".repeat(filled),
                "░".repeat(16 - filled)
            ),
            app.theme.title,
        ),
    ])
}

fn render_event_modal(f: &mut Frame, app: &App, area: Rect) {
    let modal_area = centered_rect(60, 50, area);
    f.render_widget(Clear, modal_area);
    let events = app.events.iter().rev().take(10).collect::<Vec<_>>();
    if events.is_empty() {
        return;
    }
    let event = events[app.selected_event_index.min(events.len() - 1)];
    let block = modal_block(app, " EVENT DIAGNOSTIC INSPECTOR ");
    f.render_widget(
        Paragraph::new(event_modal_lines(app, event))
            .block(block)
            .alignment(Alignment::Left),
        modal_area,
    );
}

fn event_modal_lines(app: &App, event: &RegimeEvent) -> Vec<Line<'static>> {
    let rule = "────────────────────────────────────────────────────────────";
    vec![
        Line::from(Span::styled(
            "🔬 TRANSITION DIAGNOSTIC INSPECTOR",
            app.theme.title,
        )),
        Line::from(Span::styled(rule, app.theme.border)),
        labeled_line(
            "Timestamp:           ",
            format_timestamp_display(&event.timestamp_str),
            app.theme.muted,
        ),
        labeled_line(
            "Origin State:        ",
            event.from_state.display_name().to_string(),
            app.theme.gold,
        ),
        labeled_line(
            "Destination State:   ",
            event.to_state.display_name().to_string(),
            app.theme.bull,
        ),
        labeled_line(
            "Transition Price:    ",
            format!("${:.2}", event.price),
            app.theme.gold,
        ),
        Line::from(Span::styled(rule, app.theme.border)),
        Line::from(Span::styled("TRIGGER DIAGNOSTIC REASON:", app.theme.cyan)),
        Line::from(Span::styled(
            format!("  \"{}\"", event.trigger_reason),
            app.theme.title,
        )),
        Line::from(Span::styled(rule, app.theme.border)),
        Line::from(Span::styled(
            "Press [Enter] or [Esc] to return to Cockpit View",
            app.theme.muted,
        )),
    ]
}

fn labeled_line(label: &'static str, value: String, style: ratatui::style::Style) -> Line<'static> {
    Line::from(vec![Span::raw(label), Span::styled(value, style)])
}

fn render_trade_modal(f: &mut Frame, app: &App, area: Rect) {
    let modal_area = centered_rect(72, 68, area);
    f.render_widget(Clear, modal_area);
    let Some(trade) = app.paper_trades.iter().rev().nth(app.selected_trade_index) else {
        return;
    };
    f.render_widget(
        Paragraph::new(trade_detail_lines(app, trade))
            .block(modal_block(app, " TRADE DETAIL INSPECTOR "))
            .alignment(Alignment::Left),
        modal_area,
    );
}

fn trade_detail_lines(app: &App, trade: &PaperTradeRecord) -> Vec<Line<'static>> {
    let pnl_style = if trade.pnl_usd >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let mut lines = trade_identity_lines(trade);
    lines.extend(trade_cost_lines(trade));
    lines.extend([
        Line::from(Span::styled(
            format!(
                "Gross PnL: {} | Net PnL: {} ({:+.2}%)",
                signed_usd(trade.gross_pnl_usd),
                signed_usd(trade.pnl_usd),
                trade.pnl_pct
            ),
            pnl_style,
        )),
        Line::from(format!("Exit Trigger: {}", trade.exit_reason)),
        Line::from("Press [Enter] or [Esc] to return to the journal"),
    ]);
    lines
}

fn trade_identity_lines(trade: &PaperTradeRecord) -> Vec<Line<'static>> {
    vec![
        Line::from(format!(
            "Trade ID: {} | {} {}",
            trade.trade_id, trade.symbol, trade.direction
        )),
        Line::from(format!(
            "Entry Time: {}",
            format_timestamp_display(&trade.entry_timestamp_str)
        )),
        Line::from(format!(
            "Exit Time:  {}",
            format_timestamp_display(&trade.exit_timestamp_str)
        )),
        Line::from(format!(
            "ENTRY  PRIMARY {} | 1m {} | 5m {} | 15m CONTEXT {}",
            trade.entry_primary_regime,
            trade.entry_regime_1m,
            trade.entry_regime_5m,
            trade.entry_context_15m
        )),
        Line::from(format!(
            "EXIT   PRIMARY {} | 1m {} | 5m {} | 15m CONTEXT {}",
            trade.exit_primary_regime,
            trade.exit_regime_1m,
            trade.exit_regime_5m,
            trade.exit_context_15m
        )),
        Line::from(format!(
            "Entry Price: ${:.2} | Exit Price: ${:.2} | Size: {:.5} {} | {:.1}x",
            trade.entry_price, trade.exit_price, trade.size_btc, trade.symbol, trade.leverage
        )),
    ]
}

fn trade_cost_lines(trade: &PaperTradeRecord) -> Vec<Line<'static>> {
    let funding = if trade.funding_payment_usd >= 0.0 {
        format!("Funding Paid: ${:.2}", trade.funding_payment_usd)
    } else {
        format!("Funding Received: ${:.2}", trade.funding_payment_usd.abs())
    };
    vec![
        Line::from(format!(
            "Entry Fee: ${:.2} | Exit Fee: ${:.2}",
            trade.entry_fee_usd, trade.exit_fee_usd
        )),
        Line::from(funding),
        Line::from(format!("Total Net Costs: ${:.2}", trade.total_cost_usd)),
    ]
}

fn signed_usd(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn render_help_overlay(f: &mut Frame, app: &App, area: Rect) {
    if app.backend.is_apex_mm() {
        crate::apex_mm_view::render_help(f, app, area);
        return;
    }
    let modal_area = centered_rect(65, 75, area);
    f.render_widget(Clear, modal_area);
    let mut lines = help_policy_lines(app);
    lines.extend(help_control_lines(app));
    f.render_widget(
        Paragraph::new(lines)
            .block(modal_block(app, " COCKPIT HELP & ENGINE ARCHITECTURE "))
            .alignment(Alignment::Left),
        modal_area,
    );
}

fn help_policy_lines(app: &App) -> Vec<Line<'static>> {
    let rule = "───────────────────────────────────────────────────────────────────";
    let mut lines = vec![
        Line::from(Span::styled(
            "HYPERVECTOR CANONICAL REGIME POLICY & KEYBINDINGS",
            app.theme.title,
        )),
        Line::from(Span::styled(rule, app.theme.border)),
        Line::from(Span::styled(
            "BACKEND REGIME CLASSIFICATION ROLES:",
            app.theme.gold,
        )),
    ];
    lines.extend(help_regime_lines(app));
    lines.extend([
        Line::from(Span::styled(rule, app.theme.border)),
        Line::from(Span::styled("SCORE SEMANTICS:", app.theme.gold)),
        Line::from(
            "  Structure strength is an EMA-gap percentile diagnostic, not an ML probability or gate.",
        ),
        Line::from(Span::styled(rule, app.theme.border)),
        Line::from(Span::styled(
            "INTERACTIVE KEYBOARD CONTROLS:",
            app.theme.cyan,
        )),
    ]);
    lines
}

fn help_regime_lines(app: &App) -> Vec<Line<'static>> {
    vec![
        Line::from(Span::styled(
            "  TREND_UP       : authoritative 5m positive trend structure",
            app.theme.bull,
        )),
        Line::from(Span::styled(
            "  TREND_DOWN     : authoritative 5m negative trend structure",
            app.theme.bear,
        )),
        Line::from(Span::styled(
            "  BREAKOUT       : matching directional 1m and 5m breakout confirmation",
            app.theme.coiling,
        )),
        Line::from(Span::styled(
            "  TRANSITION     : mixed 5m structure; entry blocked",
            app.theme.carry,
        )),
        Line::from(Span::styled(
            "  RANGE          : 5m range/chop/compression structure; entry blocked",
            app.theme.chop,
        )),
        Line::from(Span::styled(
            "  UNKNOWN        : incomplete warmup; entry blocked",
            app.theme.muted,
        )),
        Line::from(Span::styled(
            "  15m context is reported but is not an entry veto",
            app.theme.gold,
        )),
    ]
}

fn help_control_lines(app: &App) -> Vec<Line<'static>> {
    vec![
        control_line(
            app,
            "  [Tab / 1-4]   ",
            "Switch View (1: Dashboard, 2: Regime, 3: Chart, 4: Config)",
        ),
        control_line(
            app,
            "  [Space]       ",
            "Toggle Play / Pause Real-time Stream",
        ),
        control_line(
            app,
            "  [← / →]       ",
            "Step Backwards / Forwards through History",
        ),
        control_line(
            app,
            "  [↑ / ↓ j/k]   ",
            "Navigate Recent Transition Event Rows",
        ),
        control_line(
            app,
            "  [Enter]       ",
            "Open Transition Event Diagnostic Inspector Modal",
        ),
        control_line(
            app,
            "  [s]           ",
            "Cycle Playback Speed (1.0x -> 2.0x -> 5.0x -> 10.0x)",
        ),
        control_line(app, "  [t]           ", "Cycle Timeframe (1m -> 5m -> 15m)"),
        control_line(app, "  [r]           ", "Reset Scrub Position to Start"),
        control_line(
            app,
            "  [? / h]       ",
            "Toggle this Help & Rules Overlay Window",
        ),
        control_line(app, "  [q / Esc]     ", "Dismiss Overlay / Quit Cockpit"),
    ]
}

fn control_line(app: &App, key: &'static str, description: &'static str) -> Line<'static> {
    Line::from(vec![
        Span::styled(key, app.theme.gold),
        Span::raw(description),
    ])
}

fn modal_block<'a>(app: &App, title: &'static str) -> Block<'a> {
    Block::default()
        .title(title)
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active)
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(vertical[1])[1]
}
