//! Ultra High-Density 2-Screen Telemetry UI Rendering Engine for Hypervector Regime Cockpit v2.0.

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{
        BarChart, Block, BorderType, Borders, Clear, Gauge, Paragraph, Row, Sparkline, Table,
    },
    Frame,
};

use crate::app::App;
use crate::model::RegimeState;

pub fn draw(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Top Telemetry Header Bar
            Constraint::Min(20),    // Active View Screen Content (Screen 1 or Screen 2)
            Constraint::Length(3),  // Command Keybindings Footer Bar
        ])
        .split(f.area());

    render_header(f, app, chunks[0]);

    if app.active_tab == 0 {
        render_screen_regime_detection(f, app, chunks[1]);
    } else {
        render_screen_strategy_policy(f, app, chunks[1]);
    }

    render_footer(f, app, chunks[2]);

    if app.show_event_detail_modal {
        render_event_modal(f, app, f.area());
    }

    if app.show_help_overlay {
        render_help_overlay(f, app, f.area());
    }
}

fn render_header(f: &mut Frame, app: &App, area: Rect) {
    let (mode_str, mode_style) = match (app.is_live, app.is_synthetic) {
        (true, false) => ("🟢 REAL-TIME LIVE", app.theme.bull),
        (true, true) => ("⚠️ DEMO PLAYBACK (Synthetic Live)", app.theme.coiling),
        (false, false) => ("▶️ HISTORICAL PLAYBACK", app.theme.cyan),
        (false, true) => ("▶️ DEMO PLAYBACK (Synthetic)", app.theme.gold),
    };
    let status_str = if app.is_playing { "PLAYING" } else { "PAUSED" };

    let tab1_style = if app.active_tab == 0 { app.theme.highlight } else { app.theme.muted };
    let tab2_style = if app.active_tab == 1 { app.theme.highlight } else { app.theme.muted };

    let text = vec![Line::from(vec![
        Span::styled(" ⚡ HYPERVECTOR ENGINE ", app.theme.title),
        Span::raw("│ "),
        Span::styled(" [1] REGIME DETECTION ", tab1_style),
        Span::raw("│ "),
        Span::styled(" [2] STRATEGY POLICY ", tab2_style),
        Span::raw("│ "),
        Span::styled(format!("SYMBOL: {}", app.symbol), app.theme.gold),
        Span::raw(" │ "),
        Span::styled(format!("TF: {}", app.timeframe), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(mode_str, mode_style),
        Span::raw(" │ "),
        Span::styled(format!("[{}] ({:.1}x)", status_str, app.playback_speed), app.theme.header),
    ])];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(text).block(block).alignment(Alignment::Left);
    f.render_widget(p, area);
}

// ============================================================================
// SCREEN 1: REGIME DETECTION ENGINE ONLY (FULL DENSITY GRAPHICAL DASHBOARD)
// ============================================================================
fn render_screen_regime_detection(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),  // 1. Top Telemetry Grid (Regime + MTF + Microstructure)
            Constraint::Length(8),  // 2. Visual Graphics Row (Orderbook BarChart + Regime Histogram BarChart)
            Constraint::Length(8),  // 3. Trajectory & Volatility Compression Sparklines
            Constraint::Length(5),  // 4. Compact Half-Height Transition Audit Log Table
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Top Telemetry Row
    let top_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42), // Active Regime & Conviction Box
            Constraint::Percentage(28), // MTF Hysteresis Matrix
            Constraint::Percentage(30), // L2 Microstructure & Flow
        ])
        .split(main_chunks[0]);

    let (state_style, state_label) = match snap.state {
        RegimeState::BullMomentum => (app.theme.bull, "🔥 TREND_UP (BULL MOMENTUM EXPANSION)"),
        RegimeState::BearMomentum => (app.theme.bear, "🔻 TREND_DOWN (BEAR MOMENTUM EXPANSION)"),
        RegimeState::VolatilityCoiling => (app.theme.coiling, "⚡ BREAKOUT (VOLATILITY COILING COMPRESSION)"),
        RegimeState::FundingCarry => (app.theme.carry, "💰 TRANSITION (FUNDING CARRY REVERSAL)"),
        RegimeState::RangeChop => (app.theme.chop, "🛡️ RANGE (RANGE CHOP / HIGH FRICTION)"),
    };

    let conf_pct = (snap.confidence * 100.0).clamp(0.0, 100.0);
    let conf_bar_len = ((conf_pct / 100.0) * 16.0) as usize;
    let conf_fill = "█".repeat(conf_bar_len);
    let conf_empty = "░".repeat(16 - conf_bar_len);

    let banner_text = vec![
        Line::from(vec![Span::styled(state_label, state_style)]),
        Line::from(vec![
            Span::raw("Primary TA Label: "),
            Span::styled(snap.state.primary_label(), app.theme.gold),
            Span::raw(" │ Market Phase: "),
            Span::styled(
                match snap.state {
                    RegimeState::BullMomentum => "IMPULSE UPTREND",
                    RegimeState::BearMomentum => "IMPULSE DOWNTREND",
                    RegimeState::VolatilityCoiling => "BBWP COMPRESSION",
                    RegimeState::FundingCarry => "CARRY REVERSAL",
                    RegimeState::RangeChop => "HIGH FRICTION CHOP",
                },
                app.theme.title,
            ),
        ]),
        Line::from(vec![
            Span::raw("Model Conviction: "),
            Span::styled(format!("[{}{}] {:.1}%", conf_fill, conf_empty, conf_pct), app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("Mark Price: "),
            Span::styled(format!("${:.2}", snap.price), app.theme.gold),
            Span::raw(" │ High: "),
            Span::styled(format!("${:.2}", snap.high), app.theme.bull),
            Span::raw(" │ Low: "),
            Span::styled(format!("${:.2}", snap.low), app.theme.bear),
        ]),
        Line::from(vec![
            Span::raw("Timestamp: "),
            Span::styled(&snap.timestamp_str, app.theme.muted),
            Span::raw(" │ Volume: "),
            Span::styled(format!("{:.1} BTC", snap.volume), app.theme.title),
        ]),
    ];

    let banner_block = Block::default()
        .title(" ACTIVE MARKET REGIME TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Thick)
        .border_style(state_style);

    f.render_widget(Paragraph::new(banner_text).block(banner_block), top_chunks[0]);

    // MTF Hysteresis Matrix
    let mtf_text = vec![
        Line::from(vec![
            Span::raw(" 1m Trend: "),
            Span::styled(
                format!(" [{}] ", snap.trend_1m),
                if snap.trend_1m == "BULL" { app.theme.bull } else if snap.trend_1m == "BEAR" { app.theme.bear } else { app.theme.chop },
            ),
            Span::styled("ZLEMA Hysteresis", app.theme.muted),
        ]),
        Line::from(vec![
            Span::raw(" 5m Trend: "),
            Span::styled(
                format!(" [{}] ", snap.trend_5m),
                if snap.trend_5m == "BULL" { app.theme.bull } else if snap.trend_5m == "BEAR" { app.theme.bear } else { app.theme.chop },
            ),
            Span::styled("ZLEMA Hysteresis", app.theme.muted),
        ]),
        Line::from(vec![
            Span::raw("15m Trend: "),
            Span::styled(
                format!(" [{}] ", snap.trend_15m),
                if snap.trend_15m == "BULL" { app.theme.bull } else if snap.trend_15m == "BEAR" { app.theme.bear } else { app.theme.chop },
            ),
            Span::styled("ZLEMA Hysteresis", app.theme.muted),
        ]),
        Line::from(vec![
            Span::raw("Alignment: "),
            Span::styled(
                if snap.trend_1m == snap.trend_5m && snap.trend_5m == snap.trend_15m {
                    "FULL 3-TF ALIGNMENT"
                } else {
                    "PARTIAL ALIGNMENT"
                },
                app.theme.title,
            ),
        ]),
        Line::from(vec![
            Span::raw("Lookahead Guard: "),
            Span::styled("ACTIVE (Shift+Right)", app.theme.bull),
        ]),
    ];

    let mtf_block = Block::default()
        .title(" MTF HYSTERESIS MATRIX ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(mtf_text).block(mtf_block), top_chunks[1]);

    // L2 Microstructure OPI Dial
    let opi_ratio = ((snap.opi + 1.0) / 2.0).clamp(0.0, 1.0);
    let opi_gauge = Gauge::default()
        .block(
            Block::default()
                .title(format!(" L2 ORDERBOOK OPI ({:.2}) ", snap.opi))
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .gauge_style(if snap.opi >= 0.0 { app.theme.bull } else { app.theme.bear })
        .percent((opi_ratio * 100.0) as u16)
        .label(format!("Spread: {:.1}bps │ Depth: {:.2}x Ratio", snap.spread_bps, snap.bid_depth_ratio));

    f.render_widget(opi_gauge, top_chunks[2]);

    // 2. Visual Graphics Row (Orderbook BarChart + Regime Histogram BarChart)
    let graphic_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(50), // L2 Orderbook Liquidity Depth BarChart
            Constraint::Percentage(50), // 5-State Regime Distribution BarChart
        ])
        .split(main_chunks[1]);

    let bid_val = (snap.bid_depth_ratio * 100.0) as u64;
    let ask_val = (100.0 / snap.bid_depth_ratio.max(0.1)) as u64;

    let ob_barchart = BarChart::default()
        .block(
            Block::default()
                .title(" L2 ORDERBOOK LIQUIDITY STACK (BID vs ASK DEPTH) ")
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&[("Bid Depth", bid_val), ("Ask Depth", ask_val)])
        .bar_width(12)
        .bar_gap(4)
        .bar_style(app.theme.bull)
        .value_style(app.theme.gold);

    f.render_widget(ob_barchart, graphic_chunks[0]);

    let regime_hist_data = [
        ("BULL", if snap.state == RegimeState::BullMomentum { 90 } else { 30 }),
        ("BEAR", if snap.state == RegimeState::BearMomentum { 90 } else { 20 }),
        ("COIL", if snap.state == RegimeState::VolatilityCoiling { 90 } else { 15 }),
        ("CARRY", if snap.state == RegimeState::FundingCarry { 90 } else { 25 }),
        ("CHOP", if snap.state == RegimeState::RangeChop { 90 } else { 40 }),
    ];

    let regime_barchart = BarChart::default()
        .block(
            Block::default()
                .title(" HISTORICAL REGIME DISTRIBUTION PROFILE ")
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&regime_hist_data)
        .bar_width(8)
        .bar_gap(2)
        .bar_style(app.theme.cyan)
        .value_style(app.theme.gold);

    f.render_widget(regime_barchart, graphic_chunks[1]);

    // 3. Trajectory & Volatility Compression Sparklines
    let sparkline_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(main_chunks[2]);

    let prices = app.sparkline_price_data();
    let sparkline_price = Sparkline::default()
        .block(
            Block::default()
                .title(format!(" PRICE TRAJECTORY (${:.2}) ", snap.price))
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&prices)
        .style(app.theme.cyan);

    f.render_widget(sparkline_price, sparkline_chunks[0]);

    let bbwps = app.sparkline_bbwp_data();
    let sparkline_bbwp = Sparkline::default()
        .block(
            Block::default()
                .title(format!(
                    " BBWP COMPRESSION ({:.1}%) {} ",
                    snap.bbwp_percentile,
                    if snap.bbwp_percentile < 20.0 { "[COILING EXTREME]" } else { "" }
                ))
                .title_style(app.theme.gold)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&bbwps)
        .style(if snap.bbwp_percentile < 20.0 { app.theme.coiling } else { app.theme.cyan });

    f.render_widget(sparkline_bbwp, sparkline_chunks[1]);

    // 4. Compact Half-Height Transition Audit Log Table (5 rows height)
    render_event_log(f, app, main_chunks[3]);
}

// ============================================================================
// SCREEN 2: STRATEGY POLICY & RISK ALLOCATION ENGINE ONLY
// ============================================================================
fn render_screen_strategy_policy(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(10), // Dynamic Leverage & Position Sizing Engine
            Constraint::Length(10), // Strategy Components & Portfolio Allocation Grid
            Constraint::Min(6),     // Policy Risk & Execution Rules Diagnostics
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Dynamic Leverage & Position Sizing Engine
    let lev_pct = ((snap.dynamic_leverage / snap.max_leverage) * 100.0).clamp(0.0, 100.0);
    let lev_bar_len = ((lev_pct / 100.0) * 20.0) as usize;
    let lev_fill = "█".repeat(lev_bar_len);
    let lev_empty = "░".repeat(20 - lev_bar_len);

    let lw_pct = (snap.long_weight / 2.0).clamp(0.0, 1.0);
    let lw_len = (lw_pct * 16.0) as usize;
    let lw_fill = "█".repeat(lw_len);
    let lw_empty = "░".repeat(16 - lw_len);

    let sw_pct = (snap.short_weight / 2.0).clamp(0.0, 1.0);
    let sw_len = (sw_pct * 16.0) as usize;
    let sw_fill = "█".repeat(sw_len);
    let sw_empty = "░".repeat(16 - sw_len);

    let net_weight = snap.long_weight - snap.short_weight;
    let (net_str, net_style) = if net_weight > 0.0 {
        (format!("+{:.2}x NET LONG", net_weight), app.theme.bull)
    } else if net_weight < 0.0 {
        (format!("{:.2}x NET SHORT", net_weight), app.theme.bear)
    } else {
        ("0.00x FLAT (Net Position 0.0 / Dual Stop Breakout)".into(), app.theme.gold)
    };

    let policy_text = vec![
        Line::from(vec![
            Span::raw("Dynamic Leverage:     "),
            Span::styled(
                format!("[{}{}] {:.2}x / {:.1}x Max Cap", lev_fill, lev_empty, snap.dynamic_leverage, snap.max_leverage),
                app.theme.gold,
            ),
        ]),
        Line::from(vec![
            Span::raw("Leverage Scaling:     "),
            Span::styled("L_dynamic = clamp(L_cap * Conviction * (1 + |OPI| * 0.5), 1.0, L_cap)", app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("Long Alloc Weight:    "),
            Span::styled(format!("[{}{}] {:.2}x Target Weight", lw_fill, lw_empty, snap.long_weight), app.theme.bull),
        ]),
        Line::from(vec![
            Span::raw("Short Alloc Weight:   "),
            Span::styled(format!("[{}{}] {:.2}x Target Weight", sw_fill, sw_empty, snap.short_weight), app.theme.bear),
        ]),
        Line::from(vec![
            Span::raw("Net Position Exposure: "),
            Span::styled(net_str, net_style),
            Span::raw(" │ Venue Accounting: "),
            Span::styled("Hyperliquid Single Position Netting Active", app.theme.title),
        ]),
        Line::from(vec![
            Span::raw("Execution Policy:     "),
            Span::styled(
                if snap.taker_allowed { "TAKERS PERMITTED (Impulse High Conviction)" } else { "MAKER ORDERS ONLY (Spread Guard Active)" },
                if snap.taker_allowed { app.theme.bull } else { app.theme.gold },
            ),
        ]),
        Line::from(vec![
            Span::raw("Funding Carry Z-Score: "),
            Span::styled(format!("{:.2}", snap.funding_zscore), app.theme.carry),
            Span::raw(" │ Wilder RSI (14): "),
            Span::styled(format!("{:.1}", snap.rsi), app.theme.cyan),
        ]),
    ];

    let policy_block = Block::default()
        .title(" DYNAMIC LEVERAGE & NET POSITION SIZING ENGINE (Hyperliquid 1 Position / Symbol Netting) ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(policy_text).block(policy_block), main_chunks[0]);

    // 2. Strategy Portfolio Signals Grid
    let strategy_rows = vec![
        Row::new(vec![
            Span::styled("impulse_1m_long", app.theme.bull),
            Span::styled(if snap.long_weight > 0.0 { "ACTIVE (LONG)" } else { "INACTIVE" }, if snap.long_weight > 0.0 { app.theme.bull } else { app.theme.muted }),
            Span::styled(format!("{:.2}x", snap.long_weight), app.theme.gold),
            Span::styled(format!("{:.2}x", snap.dynamic_leverage), app.theme.cyan),
            Span::styled("1m Impulse Scalper (Hypertrader Port)", app.theme.muted),
        ]),
        Row::new(vec![
            Span::styled("impulse_1m_short", app.theme.bear),
            Span::styled(if snap.short_weight > 0.0 { "ACTIVE (SHORT)" } else { "INACTIVE" }, if snap.short_weight > 0.0 { app.theme.bear } else { app.theme.muted }),
            Span::styled(format!("{:.2}x", snap.short_weight), app.theme.gold),
            Span::styled(format!("{:.2}x", snap.dynamic_leverage), app.theme.cyan),
            Span::styled("1m Impulse Short Scalper (Hypertrader Port)", app.theme.muted),
        ]),
        Row::new(vec![
            Span::styled("pine_composite", app.theme.coiling),
            Span::styled(if snap.state == RegimeState::VolatilityCoiling { "ACTIVE (BREAKOUT)" } else { "PASS-THROUGH" }, app.theme.coiling),
            Span::styled("1.50x", app.theme.gold),
            Span::styled("2.50x", app.theme.cyan),
            Span::styled("PineScript Multi-Indicator Composite Strategy", app.theme.muted),
        ]),
        Row::new(vec![
            Span::styled("funding_carry_reversal", app.theme.carry),
            Span::styled(if snap.state == RegimeState::FundingCarry { "ACTIVE (CARRY)" } else { "INACTIVE" }, if snap.state == RegimeState::FundingCarry { app.theme.carry } else { app.theme.muted }),
            Span::styled("2.00x", app.theme.gold),
            Span::styled("3.00x", app.theme.cyan),
            Span::styled("Funding Rate Carry Mean Reversal Strategy", app.theme.muted),
        ]),
    ];

    let strategy_table = Table::new(
        strategy_rows,
        [
            Constraint::Length(25),
            Constraint::Length(18),
            Constraint::Length(14),
            Constraint::Length(14),
            Constraint::Min(30),
        ],
    )
    .header(Row::new(["Strategy Component", "Signal State", "Alloc Weight", "Dyn Leverage", "Strategy Description"].iter().map(|h| Span::styled(*h, app.theme.header))))
    .block(
        Block::default()
            .title(" REGISTERED STRATEGY PORTFOLIO SIGNALS ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(strategy_table, main_chunks[1]);

    // 3. Policy Risk Diagnostics Table
    render_event_log(f, app, main_chunks[2]);
}

fn render_event_log(f: &mut Frame, app: &App, area: Rect) {
    let header_cells = ["Timestamp", "From State", "To State", "Price", "Trigger Diagnostic"]
        .iter()
        .map(|h| Span::styled(*h, app.theme.header));
    let header = Row::new(header_cells).height(1);

    let recent_events: Vec<_> = app.events.iter().rev().take(10).collect();
    let rows = recent_events.iter().enumerate().map(|(idx, ev)| {
        let from_str = ev.from_state.display_name();
        let to_str = ev.to_state.display_name();
        let is_selected = idx == app.selected_event_index.min(recent_events.len().saturating_sub(1));

        let to_style = if is_selected {
            app.theme.highlight
        } else {
            match ev.to_state {
                RegimeState::BullMomentum => app.theme.bull,
                RegimeState::BearMomentum => app.theme.bear,
                RegimeState::VolatilityCoiling => app.theme.coiling,
                RegimeState::FundingCarry => app.theme.carry,
                RegimeState::RangeChop => app.theme.chop,
            }
        };

        let row_style = if is_selected { app.theme.highlight } else { ratatui::style::Style::default() };

        Row::new(vec![
            Span::styled(&ev.timestamp_str, if is_selected { app.theme.highlight } else { app.theme.muted }),
            Span::styled(from_str, row_style),
            Span::styled(to_str, to_style),
            Span::styled(format!("${:.2}", ev.price), if is_selected { app.theme.highlight } else { app.theme.gold }),
            Span::styled(&ev.trigger_reason, if is_selected { app.theme.highlight } else { app.theme.cyan }),
        ])
        .style(row_style)
    });

    let table = Table::new(
        rows,
        [
            Constraint::Length(19),
            Constraint::Length(42),
            Constraint::Length(42),
            Constraint::Length(12),
            Constraint::Min(25),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(
                " RECENT REGIME TRANSITION AUDIT LOG (Use [↑/↓] or [j/k] to navigate, [Enter] for details) [{}/{}] ",
                app.selected_event_index.min(recent_events.len().saturating_sub(1)) + 1,
                recent_events.len()
            ))
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(table, area);
}

fn render_footer(f: &mut Frame, app: &App, area: Rect) {
    let total = app.snapshots.len();
    let current = app.current_index + 1;
    let scrub_pct = ((current as f64 / total as f64) * 100.0).clamp(0.0, 100.0);
    let bar_len = ((scrub_pct / 100.0) * 16.0) as usize;
    let fill = "█".repeat(bar_len);
    let empty = "░".repeat(16 - bar_len);

    let help_text = Line::from(vec![
        Span::styled("[Tab / 1-2]", app.theme.gold), Span::raw(" Switch Screen View │ "),
        Span::styled("[Space]", app.theme.gold), Span::raw(" Play/Pause │ "),
        Span::styled("[←/→]", app.theme.gold), Span::raw(" Scrub │ "),
        Span::styled("[↑/↓ j/k]", app.theme.gold), Span::raw(" Select Event │ "),
        Span::styled("[Enter]", app.theme.gold), Span::raw(" Details │ "),
        Span::styled("[?]", app.theme.gold), Span::raw(" Help │ "),
        Span::styled("Scrub: ", app.theme.cyan),
        Span::styled(format!("[{}{}] {:.1}% ({}/{})", fill, empty, scrub_pct, current, total), app.theme.title),
    ]);

    let p = Paragraph::new(help_text)
        .block(Block::default().borders(Borders::ALL).border_style(app.theme.border))
        .alignment(Alignment::Center);

    f.render_widget(p, area);
}

fn render_event_modal(f: &mut Frame, app: &App, area: Rect) {
    let modal_area = centered_rect(60, 50, area);
    f.render_widget(Clear, modal_area);

    let recent_events: Vec<_> = app.events.iter().rev().take(10).collect();
    if recent_events.is_empty() {
        return;
    }
    let idx = app.selected_event_index.min(recent_events.len() - 1);
    let ev = recent_events[idx];

    let lines = vec![
        Line::from(vec![Span::styled("🔬 TRANSITION DIAGNOSTIC INSPECTOR", app.theme.title)]),
        Line::from(vec![Span::styled("────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::raw("Timestamp:           "), Span::styled(&ev.timestamp_str, app.theme.muted)]),
        Line::from(vec![Span::raw("Origin State:        "), Span::styled(ev.from_state.display_name(), app.theme.gold)]),
        Line::from(vec![Span::raw("Destination State:   "), Span::styled(ev.to_state.display_name(), app.theme.bull)]),
        Line::from(vec![Span::raw("Transition Price:    "), Span::styled(format!("${:.2}", ev.price), app.theme.gold)]),
        Line::from(vec![Span::styled("────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::styled("TRIGGER DIAGNOSTIC REASON:", app.theme.cyan)]),
        Line::from(vec![Span::styled(format!("  \"{}\"", ev.trigger_reason), app.theme.title)]),
        Line::from(vec![Span::styled("────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::styled("Press [Enter] or [Esc] to return to Cockpit View", app.theme.muted)]),
    ];

    let block = Block::default()
        .title(" EVENT DIAGNOSTIC INSPECTOR ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(lines).block(block).alignment(Alignment::Left);
    f.render_widget(p, modal_area);
}

fn render_help_overlay(f: &mut Frame, app: &App, area: Rect) {
    let modal_area = centered_rect(65, 75, area);
    f.render_widget(Clear, modal_area);

    let lines = vec![
        Line::from(vec![Span::styled("⚡ HYPERVECTOR ULTIMATE REGIME ENGINE RULES & KEYBINDINGS", app.theme.title)]),
        Line::from(vec![Span::styled("───────────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::styled("🏛️ 5-TIER MICROSTRUCTURE REGIME CLASSIFICATION RULES:", app.theme.gold)]),
        Line::from(vec![Span::styled("  🔥 TREND_UP       : 15m/5m Bull MTF + ADX > 25 + OPI >= 0.0", app.theme.bull)]),
        Line::from(vec![Span::styled("  🔻 TREND_DOWN     : 15m/5m Bear MTF + ADX > 25 + OPI <= 0.0", app.theme.bear)]),
        Line::from(vec![Span::styled("  ⚡ BREAKOUT       : BBWP Compression Percentile < 20.0 (Coiling)", app.theme.coiling)]),
        Line::from(vec![Span::styled("  💰 TRANSITION     : Funding Rate Z-Score |Z| >= 1.8 (Carry Reversal)", app.theme.carry)]),
        Line::from(vec![Span::styled("  🛡️ RANGE          : Choppiness Index > 55 or Spread > 6.0 bps", app.theme.chop)]),
        Line::from(vec![Span::styled("───────────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::styled("📊 DYNAMIC LEVERAGE SCALING (HYPERTRADER 1M IMPULSE ML):", app.theme.gold)]),
        Line::from(vec![Span::raw("  L_dynamic = clamp(L_cap * conviction * (1 + |OPI| * 0.5), 1.0, L_cap)")]),
        Line::from(vec![Span::styled("───────────────────────────────────────────────────────────────────", app.theme.border)]),
        Line::from(vec![Span::styled("⌨️ INTERACTIVE KEYBOARD CONTROLS:", app.theme.cyan)]),
        Line::from(vec![Span::styled("  [Tab / 1-2]   ", app.theme.gold), Span::raw("Switch View Screen (1: Regime Engine, 2: Strategy Policy)")]),
        Line::from(vec![Span::styled("  [Space]       ", app.theme.gold), Span::raw("Toggle Play / Pause Real-time Stream")]),
        Line::from(vec![Span::styled("  [← / →]       ", app.theme.gold), Span::raw("Step Backwards / Forwards through History")]),
        Line::from(vec![Span::styled("  [↑ / ↓ j/k]   ", app.theme.gold), Span::raw("Navigate Recent Transition Event Rows")]),
        Line::from(vec![Span::styled("  [Enter]       ", app.theme.gold), Span::raw("Open Transition Event Diagnostic Inspector Modal")]),
        Line::from(vec![Span::styled("  [s]           ", app.theme.gold), Span::raw("Cycle Playback Speed (1.0x -> 2.0x -> 5.0x -> 10.0x)")]),
        Line::from(vec![Span::styled("  [t]           ", app.theme.gold), Span::raw("Cycle Timeframe (1m -> 5m -> 15m)")]),
        Line::from(vec![Span::styled("  [r]           ", app.theme.gold), Span::raw("Reset Scrub Position to Start")]),
        Line::from(vec![Span::styled("  [? / h]       ", app.theme.gold), Span::raw("Toggle this Help & Rules Overlay Window")]),
        Line::from(vec![Span::styled("  [q / Esc]     ", app.theme.gold), Span::raw("Dismiss Overlay / Quit Cockpit")]),
    ];

    let block = Block::default()
        .title(" COCKPIT HELP & ENGINE ARCHITECTURE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(lines).block(block).alignment(Alignment::Left);
    f.render_widget(p, modal_area);
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
