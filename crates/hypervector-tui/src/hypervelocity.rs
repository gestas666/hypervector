//! Hypervelocity 40x strategy screen — the dopamine cockpit.
//!
//! Renders the strategy command bar, active position telemetry with breathing
//! orderbook depth ladder, and the unified Trade State Tracker dashboard.

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph, Sparkline},
    Frame,
};

use crate::animation;
use crate::app::App;
use crate::model::{HypervelocityTrade, RegimeState};

pub fn render_screen_hypervelocity(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6),  // Row 1: Strategy Command Bar
            Constraint::Length(11), // Row 2: Active Position + Orderbook Depth Ladder
            Constraint::Min(14),    // Row 3: Trade State Tracker Dashboard
        ])
        .split(area);

    render_command_bar(f, app, main_chunks[0]);
    render_position_and_book(f, app, main_chunks[1]);
    render_trade_state_dashboard(f, app, main_chunks[2]);
}

// ============================================================================
// ROW 1: Strategy Command Bar (6-Gate Cascade + Status)
// ============================================================================
fn render_command_bar(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let signals = app.compute_hypervelocity_signals();
    let all_green = signals.iter().all(|&s| s);

    let (state_style, state_label) = match snap.state {
        RegimeState::BullMomentum => (app.theme.bull, "BULL_MOMENTUM EXPANSION"),
        RegimeState::BearMomentum => (app.theme.bear, "BEAR_MOMENTUM EXPANSION"),
        RegimeState::VolatilityCoiling => (app.theme.coiling, "VOLATILITY COILING COMPRESSION"),
        RegimeState::FundingCarry => (app.theme.carry, "FUNDING CARRY REVERSAL"),
        RegimeState::RangeChop => (app.theme.chop, "RANGE CHOP / HIGH FRICTION"),
    };

    // Gate cascade line with animated dots
    let gate_names = ["EMA", "RSI", "CHOP", "MOM", "FUND", "BOOK"];
    let mut gate_spans: Vec<Span> = Vec::new();
    for (i, (&ok, name)) in signals.iter().zip(gate_names.iter()).enumerate() {
        let pulse_val = animation::pulse(app.tick_count + i as u64 * 3, 30);
        let dot = if ok {
            Span::styled("●", app.theme.bull)
        } else {
            Span::styled("◉", app.theme.gate_blocked)
        };
        let label_style = if ok {
            Style::default().fg(ratatui::style::Color::Rgb(
                (180.0 + 75.0 * pulse_val) as u8,
                (210.0 + 45.0 * pulse_val) as u8,
                (180.0 + 75.0 * pulse_val) as u8,
            ))
        } else {
            app.theme.muted
        };
        gate_spans.push(Span::styled(format!("[{}] {} ", i + 1, name), app.theme.muted));
        gate_spans.push(dot);
        gate_spans.push(Span::styled(if ok { " OK " } else { " NO " }, label_style));
    }

    let status_line = if all_green {
        let dir_arrow = if snap.long_weight > 0.0 { "▲ LONG" } else if snap.short_weight > 0.0 { "▼ SHORT" } else { "◆ FLAT" };
        Span::styled(
            format!("▶ ALL 6 GATES GREEN — ENTRY AUTHORIZED — {} — {}x LEVERAGE", dir_arrow, 40),
            app.theme.bull,
        )
    } else {
        let blocked: Vec<&str> = signals.iter().enumerate()
            .filter(|(_, ok)| !**ok)
            .map(|(i, _)| gate_names[i])
            .collect();
        Span::styled(
            format!("◉ GATE(S) BLOCKED: {} — WAITING", blocked.join(", ")),
            app.theme.gate_blocked,
        )
    };

    let text = vec![
        Line::from(vec![
            Span::styled("█ HYPERVELOCITY 40x █", app.theme.gold),
            Span::raw("  "),
            Span::styled(state_label, state_style),
            Span::raw("  "),
            Span::styled(format!("15m {} LOCK", snap.trend_15m), if snap.trend_15m == "BULL" { app.theme.bull } else if snap.trend_15m == "BEAR" { app.theme.bear } else { app.theme.chop }),
        ]),
        Line::from(gate_spans),
        Line::from(vec![status_line]),
    ];

    let block = Block::default()
        .title(" STRATEGY COMMAND ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(if all_green { app.theme.bull } else { app.theme.border_active });

    f.render_widget(Paragraph::new(text).block(block), area);
}

// ============================================================================
// ROW 2: Active Position PnL + L2 Orderbook Depth Ladder (side by side)
// ============================================================================
fn render_position_and_book(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);

    render_position_panel(f, app, chunks[0]);
    render_book_ladder(f, app, chunks[1]);
}

fn render_position_panel(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let pos = &app.active_position;

    let (direction, dir_style, lev, entry_price, size_btc) = if pos.is_active() {
        let dir_icon = if pos.direction == "LONG" { "▲ LONG" } else { "▼ SHORT" };
        let style = if pos.direction == "LONG" { app.theme.bull } else { app.theme.bear };
        (dir_icon, style, pos.leverage, pos.entry_price, pos.size_btc)
    } else {
        ("◆ FLAT", app.theme.muted, 0.0, snap.price, 0.0)
    };

    let tp1_pct = app.config.fixed_tp_pct * lev.max(1.0);
    let sl_pct = app.config.fixed_sl_pct * lev.max(1.0);

    let (margin_pct, peak_pct, unrealized_pnl) = if pos.is_active() {
        let mgn = if pos.direction == "LONG" {
            ((snap.price - entry_price) / entry_price * lev * 100.0 * 100.0).round() / 100.0
        } else {
            ((entry_price - snap.price) / entry_price * lev * 100.0 * 100.0).round() / 100.0
        };
        let peak = mgn.max(pos.peak_margin_pct);
        let upnl = mgn / 100.0 * (pos.entry_equity * 0.25);
        (mgn, peak, upnl)
    } else {
        (0.0, 0.0, 0.0)
    };

    let pnl_sign = if unrealized_pnl >= 0.0 { "+" } else { "" };

    // Margin return bar with gradient
    let bar_width = 40usize;
    let filled = ((margin_pct.abs() / tp1_pct.max(0.01)).min(1.0) * bar_width as f64) as usize;
    let peak_filled = ((peak_pct.abs() / tp1_pct.max(0.01)).min(1.0) * bar_width as f64) as usize;
    let filled = filled.min(bar_width);
    let peak_filled = peak_filled.min(bar_width);

    let mut bar_spans: Vec<Span> = Vec::new();
    let mut peak_spans: Vec<Span> = Vec::new();
    for i in 0..bar_width {
        let zone_pct = (i as f64 / bar_width as f64) * tp1_pct;
        let color = animation::gradient_color(zone_pct, app.tick_count);
        let ghost_color = animation::gradient_color(zone_pct, 0);

        let ch = if i < filled { '█' } else { '░' };
        bar_spans.push(Span::styled(ch.to_string(), Style::default().fg(color)));

        let pch = if i < peak_filled { '▒' } else { ' ' };
        peak_spans.push(Span::styled(pch.to_string(), Style::default().fg(ghost_color)));
    }

    let entry_display = if pos.is_active() {
        Span::styled(format!("${:.2}", entry_price), app.theme.title)
    } else {
        Span::styled("N/A", app.theme.muted)
    };

    let size_display = if pos.is_active() {
        Span::styled(format!("{:.5} BTC", size_btc), app.theme.gold)
    } else {
        Span::styled("0.00000 BTC", app.theme.muted)
    };

    let text = vec![
        Line::from(vec![
            Span::raw("SIZE  "),
            size_display,
            Span::raw("  │  ENTRY  "),
            entry_display,
            Span::raw("  │  MARK  "),
            Span::styled(format!("${:.2}", snap.price), app.theme.gold),
            Span::raw("  "),
            Span::styled(direction, dir_style),
        ]),
        Line::from(vec![Span::raw("")]),
        Line::from({
            let mut parts: Vec<Span> = vec![Span::raw("MARGIN  ")];
            parts.extend(bar_spans);
            parts.push(Span::styled(format!("  {:.2}% / {:.2}%", margin_pct, tp1_pct), app.theme.gold));
            parts
        }),
        Line::from({
            let mut parts: Vec<Span> = vec![Span::raw("PEAK    ")];
            parts.extend(peak_spans);
            parts.push(Span::styled(format!("  peak {:.2}%", peak_pct), app.theme.bar_ghost));
            parts
        }),
        Line::from(vec![
            Span::styled(format!("U/PNL {}{:.2}  │  TP {:.2}%  │  SL {:.2}%  │  {:.1}x LEV", pnl_sign, unrealized_pnl.abs(), tp1_pct, sl_pct, lev), app.theme.muted),
        ]),
    ];

    let block = Block::default()
        .title(" ACTIVE POSITION ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(if pos.is_active() { dir_style } else { app.theme.border_active });

    f.render_widget(Paragraph::new(text).block(block), area);
}

fn render_book_ladder(f: &mut Frame, app: &App, area: Rect) {
    let bs = &app.book_state;

    let mut lines: Vec<Line> = Vec::new();

    // Ask side (top 5 levels, descending: highest ask first)
    for i in (0..bs.ask_levels.len()).rev() {
        let lvl = &bs.ask_levels[i];
        let max_sz = bs.ask_levels.iter().map(|l| l.size).fold(0.0f64, f64::max)
            .max(bs.bid_levels.iter().map(|l| l.size).fold(0.0f64, f64::max))
            .max(0.01);
        let bar_len = ((lvl.size / max_sz) * 18.0).max(1.0) as usize;
        let breath = animation::bar_breath(app.tick_count, i);
        let flash = animation::depth_flash(app.tick_count, bs.ask_last_change.get(i).copied().unwrap_or(0));
        let bar = "█".repeat((bar_len as f64 * breath).max(1.0) as usize);

        let color = if flash > 1.0 {
            Style::default().fg(ratatui::style::Color::Rgb(
                (220.0 * flash).min(255.0) as u8,
                (50.0 / flash).max(30.0) as u8,
                (70.0 / flash).max(40.0) as u8,
            ))
        } else {
            app.theme.depth_ask
        };

        lines.push(Line::from(vec![
            Span::styled(format!("ASK  ${:.2}  ", lvl.price), app.theme.bear),
            Span::styled(bar, color),
            Span::styled(format!(" {:.2}", lvl.size), app.theme.muted),
        ]));
    }

    // Spread line
    let spread_style = if bs.spread_bps <= 3.0 {
        app.theme.bull
    } else if bs.spread_bps <= 6.0 {
        app.theme.coiling
    } else {
        app.theme.bear
    };
    lines.push(Line::from(vec![
        Span::styled(
            format!("───── SPREAD {:.1} bps ─────", bs.spread_bps),
            spread_style,
        ),
    ]));

    // Bid side (top 5 levels)
    for i in 0..bs.bid_levels.len() {
        let lvl = &bs.bid_levels[i];
        let max_sz = bs.ask_levels.iter().map(|l| l.size).fold(0.0f64, f64::max)
            .max(bs.bid_levels.iter().map(|l| l.size).fold(0.0f64, f64::max))
            .max(0.01);
        let bar_len = ((lvl.size / max_sz) * 18.0).max(1.0) as usize;
        let breath = animation::bar_breath(app.tick_count, i);
        let flash = animation::depth_flash(app.tick_count, bs.bid_last_change.get(i).copied().unwrap_or(0));
        let bar = "█".repeat((bar_len as f64 * breath).max(1.0) as usize);

        let color = if flash > 1.0 {
            Style::default().fg(ratatui::style::Color::Rgb(
                0_u8,
                (200.0 * flash).min(255.0) as u8,
                (100.0 / flash).max(60.0) as u8,
            ))
        } else {
            app.theme.depth_bid
        };

        lines.push(Line::from(vec![
            Span::styled(format!("BID  ${:.2}  ", lvl.price), app.theme.bull),
            Span::styled(bar, color),
            Span::styled(format!(" {:.2}", lvl.size), app.theme.muted),
        ]));
    }

    // Footer with book quality dots
    let gate_dot = if bs.gate_ok {
        Span::styled("●", app.theme.bull)
    } else {
        Span::styled("◉", app.theme.gate_blocked)
    };
    let opi_arrow = if bs.opi >= 0.0 {
        Span::styled("▲", app.theme.bull)
    } else {
        Span::styled("▼", app.theme.bear)
    };

    lines.push(Line::from(vec![
        Span::raw("BOOK: "),
        gate_dot,
        Span::styled(format!(" {}  │  OPI {:.2} ", if bs.gate_ok { "OK" } else { &bs.gate_reason }, bs.opi), app.theme.muted),
        opi_arrow,
        Span::raw("  │  "),
        Span::styled("MAKER FILLS", app.theme.bull),
    ]));

    let block = Block::default()
        .title(" LIVE L2 DEPTH LADDER ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(lines).block(block), area);
}

// ============================================================================
// ROW 3: Trade State Tracker — The Unified Dashboard
// ============================================================================
fn render_trade_state_dashboard(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(7),  // Stats row (3 columns)
            Constraint::Min(7),     // Per-trade breakdown + equity sparkline
        ])
        .split(area);

    render_stats_row(f, app, chunks[0]);
    render_trade_breakdown_and_equity(f, app, chunks[1]);
}

fn render_stats_row(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(33),
            Constraint::Percentage(34),
            Constraint::Percentage(33),
        ])
        .split(area);

    render_all_time_stats(f, app, chunks[0]);
    render_run_stats(f, app, chunks[1]);
    render_return_distribution(f, app, chunks[2]);
}

fn render_all_time_stats(f: &mut Frame, app: &App, area: Rect) {
    let stats = &app.paper_stats;
    let win_pct = stats.win_rate_pct;

    let win_bar_len = ((win_pct / 100.0) * 18.0) as usize;
    let loss_bar_len = 18 - win_bar_len;
    let win_fill = "█".repeat(win_bar_len);
    let loss_fill = "░".repeat(loss_bar_len);

    let pf_str = if stats.losses == 0 {
        "∞ (NO LOSSES)".to_string()
    } else {
        format!("{:.2}", stats.profit_factor)
    };

    let win_style = if win_pct >= 90.0 {
        let pulse_val = animation::pulse(app.tick_count, 20);
        Style::default().fg(ratatui::style::Color::Rgb(
            (255.0 * (0.85 + 0.15 * pulse_val)) as u8,
            (215.0 * (0.85 + 0.15 * pulse_val)) as u8,
            0,
        )).add_modifier(Modifier::BOLD)
    } else {
        app.theme.bull
    };

    let text = vec![
        Line::from(vec![
            Span::raw("TRADES  "), Span::styled(format!("{}", stats.total_trades), app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("WINS/LOSS  "),
            Span::styled(format!("{}/{}  ", stats.wins, stats.losses), app.theme.title),
            Span::styled(win_fill, app.theme.bull),
            Span::styled(loss_fill, app.theme.bear),
        ]),
        Line::from(vec![
            Span::styled(format!("{:.1}% WIN RATE", win_pct), win_style),
        ]),
        Line::from(vec![
            Span::raw("PF  "), Span::styled(pf_str, app.theme.gold),
        ]),
        Line::from(vec![
            Span::styled(format!("AVG WIN +${:.2}  │  MAX DD -{:.2}%", stats.avg_win_usd, stats.max_drawdown_pct), app.theme.muted),
        ]),
    ];

    let block = Block::default()
        .title(" ALL-TIME ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(text).block(block), area);
}

fn render_run_stats(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let dir = &app.position_run_direction;
    let dir_icon = if dir == "LONG" { "▲" } else if dir == "SHORT" { "▼" } else { "◆" };
    let dir_style = if dir == "LONG" { app.theme.bull } else if dir == "SHORT" { app.theme.bear } else { app.theme.muted };

    let run_win_rate = if app.run_position_index > 0 {
        (app.run_wins as f64 / app.run_position_index as f64) * 100.0
    } else {
        0.0
    };

    let avg_margin = if !app.hv_trades.is_empty() {
        let recent: Vec<&HypervelocityTrade> = app.hv_trades.iter().rev().take(app.run_position_index as usize).collect();
        if recent.is_empty() { 0.0 } else { recent.iter().map(|t| t.margin_pnl_pct).sum::<f64>() / recent.len() as f64 }
    } else {
        0.0
    };

    let text = vec![
        Line::from(vec![
            Span::raw("POSITION  "),
            Span::styled(format!("#{}", app.run_position_index), app.theme.gold),
            Span::raw("  "),
            Span::styled(format!("{} {}", dir_icon, dir), dir_style),
        ]),
        Line::from(vec![
            Span::raw("W/L RUN  "),
            Span::styled(format!("{}W / {}L", app.run_wins, app.run_position_index.saturating_sub(app.run_wins)), app.theme.title),
            Span::styled(format!("  {:.0}%", run_win_rate), app.theme.bull),
        ]),
        Line::from(vec![
            Span::raw("RUN PnL  "),
            Span::styled(format!("+${:.2}", app.run_pnl), app.theme.gold),
        ]),
        Line::from(vec![
            Span::styled(format!("AVG MGN {:.2}%", avg_margin), app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("REGIME  "),
            Span::styled(snap.state.primary_label(), match snap.state {
                RegimeState::BullMomentum => app.theme.bull,
                RegimeState::BearMomentum => app.theme.bear,
                _ => app.theme.muted,
            }),
        ]),
    ];

    let block = Block::default()
        .title(" THIS RUN ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(text).block(block), area);
}

fn render_return_distribution(f: &mut Frame, app: &App, area: Rect) {
    // Build histogram buckets
    let mut buckets = [0usize; 7]; // -2, 0, +2, +4, +6, +8, +10+
    for t in &app.hv_trades {
        let m = t.margin_pnl_pct;
        let idx = if m < -1.0 { 0 } else if m < 1.0 { 1 } else if m < 3.0 { 2 } else if m < 5.0 { 3 } else if m < 7.0 { 4 } else if m < 9.0 { 5 } else { 6 };
        buckets[idx.min(6)] += 1;
    }
    let max_bucket = *buckets.iter().max().unwrap_or(&1).max(&1);
    let bar_width = 10usize;

    let labels = ["-2%", "0%", "+2%", "+4%", "+6%", "+8%", "+10%"];
    let colors = [
        app.theme.bear,
        app.theme.muted,
        app.theme.bull,
        app.theme.bull,
        app.theme.gold,
        app.theme.zone_target,
        app.theme.zone_climax,
    ];

    let mut lines: Vec<Line> = Vec::new();
    for i in 0..7 {
        let bar_len = ((buckets[i] as f64 / max_bucket as f64) * bar_width as f64).max(if buckets[i] > 0 { 1.0 } else { 0.0 }) as usize;
        let bar = "█".repeat(bar_len);
        let empty = "░".repeat(bar_width - bar_len);
        lines.push(Line::from(vec![
            Span::styled(format!("{:>4} ", labels[i]), app.theme.muted),
            Span::styled(bar, colors[i]),
            Span::styled(empty, app.theme.muted),
            Span::styled(format!(" {}", buckets[i]), app.theme.muted),
        ]));
    }

    let block = Block::default()
        .title(" RETURN DISTRIBUTION ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn render_trade_breakdown_and_equity(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);

    render_per_trade_breakdown(f, app, chunks[0]);
    render_equity_sparkline(f, app, chunks[1]);
}

fn render_per_trade_breakdown(f: &mut Frame, app: &App, area: Rect) {
    let trades: Vec<&HypervelocityTrade> = app.hv_trades.iter().rev().take(12).collect();
    let max_age = trades.len().max(1);
    let bar_max = 40usize;

    let mut lines: Vec<Line> = Vec::new();
    for (age, t) in trades.iter().enumerate() {
        let dir_icon = if t.direction == "LONG" { "▲" } else { "▼" };
        let dir_style = if t.direction == "LONG" { app.theme.bull } else { app.theme.bear };

        let bar_len = ((t.margin_pnl_pct.abs() / 12.0).min(1.0) * bar_max as f64) as usize;
        let bar_len = bar_len.min(bar_max);

        let mut bar_spans: Vec<Span> = Vec::new();
        for i in 0..bar_max {
            let ch = if i < bar_len {
                if t.pnl_usd >= 0.0 { '█' } else { '░' }
            } else {
                '·'
            };
            let zone_pct = (i as f64 / bar_max as f64) * 12.0;
            let base_color = if t.pnl_usd >= 0.0 {
                animation::gradient_color(zone_pct, 0)
            } else {
                ratatui::style::Color::Rgb(255, 60, 60)
            };
            let color = animation::aged_color(base_color, age, max_age);
            bar_spans.push(Span::styled(ch.to_string(), Style::default().fg(color)));
        }

        let exit_label = match t.exit_reason.as_str() {
            "tp1" | "tp2" => t.exit_reason.as_str(),
            "SL" => "SL",
            "OPEN" => "OPEN",
            "TREND_UP (BULL MOMENTUM EXPANSION)" => "regime",
            "TREND_DOWN (BEAR MOMENTUM EXPANSION)" => "regime",
            "BREAKOUT (VOLATILITY COILING COMPRESSION)" => "regime",
            "TRANSITION (FUNDING CARRY REVERSAL)" => "regime",
            "RANGE (RANGE CHOP / HIGH FRICTION)" => "regime",
            _ => &t.exit_reason,
        };

        let fill_color = if t.fill_type == "maker" { app.theme.bull } else { app.theme.bear };

        lines.push(Line::from({
            let mut parts: Vec<Span> = vec![
                Span::styled(format!("#{:<3} ", t.index), app.theme.muted),
                Span::styled(format!("{} {}", dir_icon, if t.direction == "LONG" { "L" } else { "S" }), dir_style),
                Span::styled(format!(" {:+.2} ", t.pnl_usd), if t.pnl_usd >= 0.0 { app.theme.bull } else { app.theme.bear }),
            ];
            parts.extend(bar_spans);
            parts.push(Span::styled(format!(" {:+.2}%", t.margin_pnl_pct), app.theme.muted));
            parts.push(Span::raw("  "));
            parts.push(Span::styled(format!("[{}]", t.fill_type), fill_color));
            parts.push(Span::styled(format!(" {}", exit_label), app.theme.muted));
            parts
        }));
    }

    let block = Block::default()
        .title(format!(" PER-TRADE BREAKDOWN (last {}) ", trades.len()))
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn render_equity_sparkline(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Length(3)])
        .split(area);

    let equity_data = app.sparkline_equity_data();
    let sparkline = Sparkline::default()
        .block(
            Block::default()
                .title(" EQUITY CURVE (60-bar rolling) ")
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&equity_data)
        .style(app.theme.bull);

    f.render_widget(sparkline, chunks[0]);

    let tp_pct = app.config.fixed_tp_pct * match app.config.leverage_mode {
        crate::model::LeverageMode::DynamicML => 2.0,
        crate::model::LeverageMode::StaticMultiplier(mult) => mult,
    };

    let text = vec![
        Line::from(vec![
            Span::styled(format!("EQUITY ${:.2}  │  +{:.1}%  │  TP {:.1}% MARGIN  │  {}x FIXED",
                app.paper_stats.current_equity,
                (app.paper_stats.current_equity - app.paper_stats.initial_capital) / app.paper_stats.initial_capital * 100.0,
                tp_pct,
                match app.config.leverage_mode {
                    crate::model::LeverageMode::DynamicML => 2.0,
                    crate::model::LeverageMode::StaticMultiplier(mult) => mult,
                }
            ), app.theme.muted),
        ]),
        Line::from(vec![
            Span::styled(format!("{} TRADES  │  {:.1}% WIN  │  {}x PF",
                app.paper_stats.total_trades,
                app.paper_stats.win_rate_pct,
                if app.paper_stats.losses == 0 { "∞".to_string() } else { format!("{:.2}", app.paper_stats.profit_factor) }
            ), app.theme.muted),
        ]),
    ];

    let block = Block::default()
        .title(" PERFORMANCE SUMMARY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(text).block(block), chunks[1]);
}
