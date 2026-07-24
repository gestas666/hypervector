//! UI rendering module for Quant TA & Microstructure Regime Detector Cockpit.

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Gauge, Paragraph, Row, Sparkline, Table,
    },
    Frame,
};

use crate::app::App;
use crate::model::RegimeState;

pub fn draw(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Header Bar
            Constraint::Length(7),  // Big Banner + MTF Matrix + OPI Gauge
            Constraint::Length(10), // Price Sparkline + BBWP + Policy Allocation Box
            Constraint::Min(6),     // Regime Transition Event Log
            Constraint::Length(3),  // Keybindings Footer
        ])
        .split(f.area());

    render_header(f, app, chunks[0]);
    render_top_dashboard(f, app, chunks[1]);
    render_center_analytics(f, app, chunks[2]);
    render_event_log(f, app, chunks[3]);
    render_footer(f, app, chunks[4]);
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
        Span::styled(" ⚡ HYPERVECTOR PERPETUALS BACKTEST ENGINE & ULTIMATE REGIME DETECTOR ", app.theme.title),
        Span::raw(" | "),
        Span::styled(format!("SYMBOL: {}", app.symbol), app.theme.gold),
        Span::raw(" | "),
        Span::styled(format!("TIMEFRAME: {}", app.timeframe), app.theme.cyan),
        Span::raw(" | "),
        Span::styled(mode_str, mode_style),
        Span::raw(" | "),
        Span::styled(format!("[{}] ({:.1}x)", status_str, app.playback_speed), app.theme.header),
    ])];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(text).block(block).alignment(Alignment::Left);
    f.render_widget(p, area);
}

fn render_top_dashboard(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(45), // Big Banner State Box
            Constraint::Percentage(25), // MTF Alignment Matrix
            Constraint::Percentage(30), // Microstructure OPI & Depth Gauge
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Big Banner State Box with Hypertrader Primary Label Badge
    let (state_style, state_label) = match snap.state {
        RegimeState::BullMomentum => (app.theme.bull, "🔥 TREND_UP (BULL MOMENTUM EXPANSION)"),
        RegimeState::BearMomentum => (app.theme.bear, "🔻 TREND_DOWN (BEAR MOMENTUM EXPANSION)"),
        RegimeState::VolatilityCoiling => (app.theme.coiling, "⚡ BREAKOUT (VOLATILITY COILING COMPRESSION)"),
        RegimeState::FundingCarry => (app.theme.carry, "💰 TRANSITION (FUNDING CARRY REVERSAL)"),
        RegimeState::RangeChop => (app.theme.chop, "🛡️ RANGE (RANGE CHOP / HIGH FRICTION)"),
    };

    let banner_text = vec![
        Line::from(vec![Span::styled(state_label, state_style)]),
        Line::from(vec![
            Span::raw("Primary TA Label: "),
            Span::styled(snap.state.primary_label(), app.theme.gold),
            Span::raw(" | Confidence: "),
            Span::styled(format!("{:.1}%", snap.confidence * 100.0), app.theme.title),
        ]),
        Line::from(vec![
            Span::raw("Price: "),
            Span::styled(format!("${:.2}", snap.price), app.theme.gold),
            Span::raw(" | Time: "),
            Span::styled(&snap.timestamp_str, app.theme.muted),
        ]),
    ];

    let banner_block = Block::default()
        .title(" ACTIVE MARKET REGIME ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Thick)
        .border_style(state_style);

    f.render_widget(Paragraph::new(banner_text).block(banner_block), chunks[0]);

    // 2. MTF Alignment Matrix
    let mtf_text = vec![
        Line::from(vec![Span::raw(" 1m Trend: "), Span::styled(&snap.trend_1m, if snap.trend_1m == "BULL" { app.theme.bull } else { app.theme.bear })]),
        Line::from(vec![Span::raw(" 5m Trend: "), Span::styled(&snap.trend_5m, if snap.trend_5m == "BULL" { app.theme.bull } else { app.theme.bear })]),
        Line::from(vec![Span::raw("15m Trend: "), Span::styled(&snap.trend_15m, if snap.trend_15m == "BULL" { app.theme.bull } else { app.theme.bear })]),
    ];

    let mtf_block = Block::default()
        .title(" MTF ALIGNMENT ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(mtf_text).block(mtf_block), chunks[1]);

    // 3. Microstructure OPI & Depth Gauge
    let opi_ratio = ((snap.opi + 1.0) / 2.0).clamp(0.0, 1.0);
    let opi_gauge = Gauge::default()
        .block(
            Block::default()
                .title(" L2 ORDERBOOK PRESSURE (OPI) ")
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .gauge_style(if snap.opi >= 0.0 { app.theme.bull } else { app.theme.bear })
        .percent((opi_ratio * 100.0) as u16)
        .label(format!("OPI: {:.2} | Spread: {:.1}bps", snap.opi, snap.spread_bps));

    f.render_widget(opi_gauge, chunks[2]);
}

fn render_center_analytics(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(60), // ASCII Sparkline Price & BBWP
            Constraint::Percentage(40), // Policy Strategy Allocation Box
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. ASCII Sparkline Price & BBWP
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
                .title(format!(" BBWP COMPRESSION PERCENTILE ({:.1}%) ", snap.bbwp_percentile))
                .title_style(app.theme.gold)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&bbwps)
        .style(if snap.bbwp_percentile < 20.0 { app.theme.coiling } else { app.theme.cyan });

    f.render_widget(sparkline_bbwp, inner_chunks[1]);

    // 2. Policy Strategy Allocation Box
    let policy_text = vec![
        Line::from(vec![Span::raw("Long Alloc Weight:  "), Span::styled(format!("{:.2}x", snap.long_weight), app.theme.bull)]),
        Line::from(vec![Span::raw("Short Alloc Weight: "), Span::styled(format!("{:.2}x", snap.short_weight), app.theme.bear)]),
        Line::from(vec![Span::raw("Max Leverage Cap:   "), Span::styled(format!("{:.1}x", snap.max_leverage), app.theme.gold)]),
        Line::from(vec![Span::raw("Taker Allowed:      "), Span::styled(if snap.taker_allowed { "YES" } else { "NO (Maker Only)" }, if snap.taker_allowed { app.theme.bull } else { app.theme.gold })]),
        Line::from(vec![Span::raw("Funding Z-Score:    "), Span::styled(format!("{:.2}", snap.funding_zscore), app.theme.carry)]),
        Line::from(vec![Span::raw("RSI (14):           "), Span::styled(format!("{:.1}", snap.rsi), app.theme.cyan)]),
    ];

    let policy_block = Block::default()
        .title(" STRATEGY ALLOCATION POLICY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(policy_text).block(policy_block), chunks[1]);
}

fn render_event_log(f: &mut Frame, app: &App, area: Rect) {
    let header_cells = ["Timestamp", "From State", "To State", "Price", "Trigger Reason"]
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
            Constraint::Length(45),
            Constraint::Length(45),
            Constraint::Length(12),
            Constraint::Min(25),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(" RECENT REGIME TRANSITION EVENTS ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(table, area);
}

fn render_footer(f: &mut Frame, app: &App, area: Rect) {
    let help_text = Line::from(vec![
        Span::styled("[Space]", app.theme.gold), Span::raw(" Play/Pause | "),
        Span::styled("[←/→]", app.theme.gold), Span::raw(" Scrub Back/Fwd | "),
        Span::styled("[s]", app.theme.gold), Span::raw(" Cycle Speed | "),
        Span::styled("[t]", app.theme.gold), Span::raw(" Timeframe | "),
        Span::styled("[r]", app.theme.gold), Span::raw(" Reset | "),
        Span::styled("[q / Esc]", app.theme.gold), Span::raw(" Quit"),
    ]);

    let p = Paragraph::new(help_text)
        .block(Block::default().borders(Borders::ALL).border_style(app.theme.border))
        .alignment(Alignment::Center);

    f.render_widget(p, area);
}
