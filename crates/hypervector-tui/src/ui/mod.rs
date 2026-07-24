//! Ultra High-Density Telemetry UI Rendering Engine for Hypervector Regime Cockpit v2.0.

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Clear, Gauge, Paragraph, Row, Sparkline, Table,
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
            Constraint::Length(9),  // Upper Telemetry Grid (Regime + MTF + Microstructure)
            Constraint::Length(12), // Analytics Grid (Sparklines + Dynamic Allocation)
            Constraint::Min(6),     // Regime Transition Event Audit Log Table
            Constraint::Length(3),  // Command Keybindings Footer Bar
        ])
        .split(f.area());

    render_header(f, app, chunks[0]);
    render_top_telemetry(f, app, chunks[1]);
    render_analytics_grid(f, app, chunks[2]);
    render_event_log(f, app, chunks[3]);
    render_footer(f, app, chunks[4]);

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

    let text = vec![Line::from(vec![
        Span::styled(" ⚡ HYPERVECTOR PERPETUALS ENGINE COCKPIT ", app.theme.title),
        Span::raw(" │ "),
        Span::styled(format!("SYMBOL: {}", app.symbol), app.theme.gold),
        Span::raw(" │ "),
        Span::styled(format!("TIMEFRAME: {}", app.timeframe), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(mode_str, mode_style),
        Span::raw(" │ "),
        Span::styled(format!("[{}] ({:.1}x)", status_str, app.playback_speed), app.theme.header),
        Span::raw(" │ "),
        Span::styled(format!("FRAME #{}", app.current_index + 1), app.theme.muted),
    ])];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(text).block(block).alignment(Alignment::Left);
    f.render_widget(p, area);
}

fn render_top_telemetry(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42), // Active Regime & Conviction Box
            Constraint::Percentage(28), // MTF Hysteresis Matrix
            Constraint::Percentage(30), // L2 Microstructure & Flow
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Active Regime Banner & Conviction
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
            Span::raw(" │ Market State: "),
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

    f.render_widget(Paragraph::new(banner_text).block(banner_block), chunks[0]);

    // 2. MTF Hysteresis Matrix
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

    f.render_widget(Paragraph::new(mtf_text).block(mtf_block), chunks[1]);

    // 3. L2 Microstructure OPI & Depth Gauge
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

    f.render_widget(opi_gauge, chunks[2]);
}

fn render_analytics_grid(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(55), // Dual Trajectory Sparklines
            Constraint::Percentage(45), // Dynamic Risk & Allocation Engine
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Dual Trajectory Sparklines
    let inner_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(chunks[0]);

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

    f.render_widget(sparkline_price, inner_chunks[0]);

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

    f.render_widget(sparkline_bbwp, inner_chunks[1]);

    // 2. Dynamic Risk & Allocation Engine
    let lev_pct = ((snap.dynamic_leverage / snap.max_leverage) * 100.0).clamp(0.0, 100.0);
    let lev_bar_len = ((lev_pct / 100.0) * 14.0) as usize;
    let lev_fill = "█".repeat(lev_bar_len);
    let lev_empty = "░".repeat(14 - lev_bar_len);

    let lw_pct = (snap.long_weight / 2.0).clamp(0.0, 1.0);
    let lw_len = (lw_pct * 12.0) as usize;
    let lw_fill = "█".repeat(lw_len);
    let lw_empty = "░".repeat(12 - lw_len);

    let sw_pct = (snap.short_weight / 2.0).clamp(0.0, 1.0);
    let sw_len = (sw_pct * 12.0) as usize;
    let sw_fill = "█".repeat(sw_len);
    let sw_empty = "░".repeat(12 - sw_len);

    let policy_text = vec![
        Line::from(vec![
            Span::raw("Long Weight:       "),
            Span::styled(format!("[{}{}] {:.2}x", lw_fill, lw_empty, snap.long_weight), app.theme.bull),
        ]),
        Line::from(vec![
            Span::raw("Short Weight:      "),
            Span::styled(format!("[{}{}] {:.2}x", sw_fill, sw_empty, snap.short_weight), app.theme.bear),
        ]),
        Line::from(vec![
            Span::raw("Dynamic Leverage:  "),
            Span::styled(
                format!("[{}{}] {:.2}x / {:.1}x Cap", lev_fill, lev_empty, snap.dynamic_leverage, snap.max_leverage),
                app.theme.gold,
            ),
        ]),
        Line::from(vec![
            Span::raw("Leverage Scaling:  "),
            Span::styled("Conviction & Orderbook Flow Scaled", app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("Execution Policy:  "),
            Span::styled(
                if snap.taker_allowed { "YES (Taker Allowed)" } else { "NO (Maker Only)" },
                if snap.taker_allowed { app.theme.bull } else { app.theme.gold },
            ),
        ]),
        Line::from(vec![
            Span::raw("Funding Z-Score:   "),
            Span::styled(format!("{:.2}", snap.funding_zscore), app.theme.carry),
            Span::raw(" │ Wilder RSI (14): "),
            Span::styled(format!("{:.1}", snap.rsi), app.theme.cyan),
        ]),
    ];

    let policy_block = Block::default()
        .title(" DYNAMIC RISK & ALLOCATION ENGINE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(policy_text).block(policy_block), chunks[1]);
}

fn render_event_log(f: &mut Frame, app: &App, area: Rect) {
    let header_cells = ["Timestamp", "From State", "To State", "Price", "Trigger Diagnostic"]
        .iter()
        .map(|h| Span::styled(*h, app.theme.header));
    let header = Row::new(header_cells).height(1);

    let rows = app.events.iter().rev().take(10).map(|ev| {
        let from_str = ev.from_state.display_name();
        let to_str = ev.to_state.display_name();
        let to_style = match ev.to_state {
            RegimeState::BullMomentum => app.theme.bull,
            RegimeState::BearMomentum => app.theme.bear,
            RegimeState::VolatilityCoiling => app.theme.coiling,
            RegimeState::FundingCarry => app.theme.carry,
            RegimeState::RangeChop => app.theme.chop,
        };

        Row::new(vec![
            Span::styled(&ev.timestamp_str, app.theme.muted),
            Span::raw(from_str),
            Span::styled(to_str, to_style),
            Span::styled(format!("${:.2}", ev.price), app.theme.gold),
            Span::styled(&ev.trigger_reason, app.theme.cyan),
        ])
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
            .title(" RECENT REGIME TRANSITION AUDIT LOG ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(table, area);
}

fn render_footer(f: &mut Frame, app: &App, area: Rect) {
    let help_text = Line::from(vec![
        Span::styled("[Space]", app.theme.gold), Span::raw(" Play/Pause │ "),
        Span::styled("[←/→]", app.theme.gold), Span::raw(" Scrub │ "),
        Span::styled("[1-3]", app.theme.gold), Span::raw(" Timeframe (1m/5m/15m) │ "),
        Span::styled("[s]", app.theme.gold), Span::raw(" Speed │ "),
        Span::styled("[?]", app.theme.gold), Span::raw(" Help Rules Overlay │ "),
        Span::styled("[q/Esc]", app.theme.gold), Span::raw(" Quit"),
    ]);

    let p = Paragraph::new(help_text)
        .block(Block::default().borders(Borders::ALL).border_style(app.theme.border))
        .alignment(Alignment::Center);

    f.render_widget(p, area);
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
        Line::from(vec![Span::styled("  [Space]       ", app.theme.gold), Span::raw("Toggle Play / Pause Real-time Stream")]),
        Line::from(vec![Span::styled("  [← / →]       ", app.theme.gold), Span::raw("Step Backwards / Forwards through History")]),
        Line::from(vec![Span::styled("  [1 / 2 / 3]   ", app.theme.gold), Span::raw("Select Timeframe (1m / 5m / 15m)")]),
        Line::from(vec![Span::styled("  [s]           ", app.theme.gold), Span::raw("Cycle Playback Speed (1.0x -> 2.0x -> 5.0x -> 10.0x)")]),
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
