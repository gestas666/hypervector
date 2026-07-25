//! Ultra High-Density 2-Screen Telemetry UI Rendering Engine for Hypervector Regime Cockpit v2.0.
//! Implements visual telemetry spec from docs/enhancements/2026-07-24-tui-regime-cockpit-eyecandy.md.

use chrono::{DateTime, NaiveDateTime, TimeZone, Utc};
use chrono_tz::{America::New_York, Tz};
use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{
        BarChart, Block, BorderType, Borders, Clear, Gauge, Paragraph, Row, Sparkline, Table,
    },
};

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::hypervelocity;
use crate::model::RegimeState;

pub fn format_timestamp_display(ts: &str) -> String {
    let fixed_ts = normalized_timestamp(ts);
    if let Some(eastern) = eastern_timestamp(&fixed_ts) {
        return eastern.format("%Y-%m-%d %H:%M:%S %Z").to_string();
    }
    if fixed_ts.contains('T') {
        let parts: Vec<&str> = fixed_ts.split('T').collect();
        let date = parts[0];
        let time = parts
            .get(1)
            .unwrap_or(&"")
            .split('.')
            .next()
            .unwrap_or("")
            .trim_end_matches('Z');
        format!("{} {}", date, time)
    } else {
        fixed_ts
    }
}

pub fn format_time_display(ts: &str) -> String {
    let fixed_ts = normalized_timestamp(ts);
    if let Some(eastern) = eastern_timestamp(&fixed_ts) {
        return eastern.format("%H:%M:%S %Z").to_string();
    }
    let time_str = if fixed_ts.contains('T') {
        fixed_ts.split('T').nth(1).unwrap_or("")
    } else if fixed_ts.contains(' ') {
        fixed_ts.split(' ').nth(1).unwrap_or("")
    } else {
        &fixed_ts
    };
    let time_clean = time_str
        .split('.')
        .next()
        .unwrap_or(time_str)
        .trim_end_matches('Z');
    if time_clean.is_empty() {
        fixed_ts.to_string()
    } else {
        time_clean.to_string()
    }
}

fn normalized_timestamp(ts: &str) -> String {
    let today = crate::data_loader::get_today_date_str();
    ts.replace("1969-12-31", &today)
        .replace("1970-01-01", &today)
}

fn eastern_timestamp(ts: &str) -> Option<DateTime<Tz>> {
    DateTime::parse_from_rfc3339(ts)
        .ok()
        .map(|value| value.with_timezone(&New_York))
        .or_else(|| eastern_from_utc_label(ts))
}

fn eastern_from_utc_label(ts: &str) -> Option<DateTime<Tz>> {
    let raw = ts.strip_suffix(" UTC")?;
    let naive = NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S").ok()?;
    Some(Utc.from_utc_datetime(&naive).with_timezone(&New_York))
}

pub fn draw(f: &mut Frame, app: &App) {
    if app.snapshots.is_empty() {
        render_backend_only(f, app);
        return;
    }
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Top Telemetry Header Bar
            Constraint::Length(3), // SRS_TUI_EC1 Regime Timeline Ribbon
            Constraint::Min(20),   // Active View Screen Content
            Constraint::Length(3), // Command Keybindings Footer Bar
        ])
        .split(f.area());

    render_header(f, app, chunks[0]);
    render_timeline_ribbon(f, app, chunks[1]);

    if app.active_tab == 0 {
        render_screen_strategy_policy(f, app, chunks[2]);
    } else if app.active_tab == 1 {
        render_screen_regime_detection(f, app, chunks[2]);
    } else {
        crate::config_view::render_backend_configuration(f, app, chunks[2]);
    }

    render_footer(f, app, chunks[3]);

    if app.show_event_detail_modal {
        render_event_modal(f, app, f.area());
    }

    if app.show_help_overlay {
        render_help_overlay(f, app, f.area());
    }
}

fn render_backend_only(f: &mut Frame, app: &App) {
    let state = match app.backend.connection {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    };
    let lines = vec![
        Line::from(format!("BACKEND {state}: {}", app.backend.status_message)),
        Line::from(format!(
            "run={} strategy={} mode={}",
            app.backend.run_id.as_deref().unwrap_or("unknown"),
            app.backend.strategy_name.as_deref().unwrap_or("unknown"),
            app.backend.execution_mode.as_deref().unwrap_or("unknown"),
        )),
        Line::from(format!(
            "equity=${:.2} trades={} position={}",
            app.paper_stats.current_equity,
            app.paper_stats.total_trades,
            app.active_position.direction,
        )),
        Line::from("Market/regime snapshots unavailable; no local fallback was generated."),
    ];
    let block = Block::default()
        .title(" READ-ONLY BACKEND TELEMETRY ")
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(lines).block(block), f.area());
}

fn render_header(f: &mut Frame, app: &App, area: Rect) {
    let spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    let spinner = spinner_frames[(app.tick_count % spinner_frames.len() as u64) as usize];

    let (mode_str, mode_style) = if app.is_live {
        (
            format!("{} REAL-TIME LIVE ORDERBOOK STREAM", spinner),
            app.theme.bull,
        )
    } else {
        ("▶️ REAL HISTORICAL MARKET DATA".into(), app.theme.cyan)
    };
    let status_str = if app.is_playing { "PLAYING" } else { "PAUSED" };

    let tab1_style = if app.active_tab == 0 {
        app.theme.highlight
    } else {
        app.theme.muted
    };
    let tab2_style = if app.active_tab == 1 {
        app.theme.highlight
    } else {
        app.theme.muted
    };
    let tab3_style = if app.active_tab == 2 {
        app.theme.highlight
    } else {
        app.theme.muted
    };

    let text = vec![Line::from(vec![
        Span::styled(" ⚡ HYPERVECTOR ENGINE ", app.theme.title),
        Span::raw("│ "),
        Span::styled(" [1] DASHBOARD ", tab1_style),
        Span::raw("│ "),
        Span::styled(" [2] REGIME DETECTION ", tab2_style),
        Span::raw("│ "),
        Span::styled(" [3] CONFIG ", tab3_style),
        Span::raw("│ "),
        Span::styled(format!("SYMBOL: {}", app.symbol), app.theme.gold),
        Span::raw(" │ "),
        Span::styled(format!("TF: {}", app.timeframe), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(mode_str, mode_style),
        Span::raw(" │ "),
        Span::styled(
            format!("[{}] ({:.1}x)", status_str, app.playback_speed),
            app.theme.header,
        ),
    ])];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(text).block(block).alignment(Alignment::Left);
    f.render_widget(p, area);
}

// High-Visual Regime Timeline Ribbon with Explicit Legend Title
fn render_timeline_ribbon(f: &mut Frame, app: &App, area: Rect) {
    if area.width < 5 || app.snapshots.is_empty() {
        return;
    }
    let total = app.snapshots.len();
    let inner_width = area.width.saturating_sub(2) as usize;
    let start = if app.current_index > inner_width / 2 {
        app.current_index - inner_width / 2
    } else {
        0
    };
    let end = (start + inner_width).min(total);

    let spans: Vec<Span> = app.snapshots[start..end]
        .iter()
        .enumerate()
        .map(|(i, snap)| {
            let idx = start + i;
            let style = match snap.state {
                RegimeState::BullMomentum => app.theme.bull,
                RegimeState::BearMomentum => app.theme.bear,
                RegimeState::VolatilityCoiling => app.theme.coiling,
                RegimeState::FundingCarry => app.theme.carry,
                RegimeState::RangeChop => app.theme.chop,
            };
            if idx == app.current_index {
                Span::styled("█", style.add_modifier(ratatui::style::Modifier::REVERSED))
            } else {
                Span::styled("█", style)
            }
        })
        .collect();

    let snap = app.current_snapshot();
    let title_str = format!(
        " 🎞️ REGIME TIMELINE (Playhead: █ Inverted) │ Active: [{}] │ HTF Lock: 15m [{}] ",
        snap.state.primary_label(),
        snap.trend_15m
    );

    let block = Block::default()
        .title(title_str)
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(Line::from(spans)).block(block), area);
}

// ============================================================================
// SCREEN 2: REGIME DETECTION ENGINE ONLY (FULL DENSITY GRAPHICAL DASHBOARD)
// ============================================================================
fn render_screen_regime_detection(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8), // 1. Top Telemetry Grid (Regime + MTF + Microstructure)
            Constraint::Length(7), // 2. Real-time Price Range & Impulse Conviction Telemetry
            Constraint::Length(7), // 3. Visual Graphics Row (Orderbook BarChart + Regime Histogram BarChart)
            Constraint::Length(7), // 4. Trajectory & Volatility Compression Sparklines
            Constraint::Length(1), // 5. SRS_TUI_EC8 Regime Distribution Bar
            Constraint::Min(6),    // 6. Expansive Audit Log Box Extending to Bottom of Screen
        ])
        .split(area);

    let snap = app.current_snapshot();

    // 1. Top Telemetry Row
    let top_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42), // Active Regime & Conviction Box
            Constraint::Percentage(28), // MTF Hysteresis Matrix
            Constraint::Percentage(30), // L2 Microstructure & Bipolar Meters
        ])
        .split(main_chunks[0]);

    let (state_style, state_label) = match snap.state {
        RegimeState::BullMomentum => (app.theme.bull, "🔥 TREND_UP (BULL MOMENTUM EXPANSION)"),
        RegimeState::BearMomentum => (app.theme.bear, "🔻 TREND_DOWN (BEAR MOMENTUM EXPANSION)"),
        RegimeState::VolatilityCoiling => (
            app.theme.coiling,
            "⚡ BREAKOUT (VOLATILITY COILING COMPRESSION)",
        ),
        RegimeState::FundingCarry => (app.theme.carry, "💰 TRANSITION (FUNDING CARRY REVERSAL)"),
        RegimeState::RangeChop => (app.theme.chop, "🛡️ RANGE (RANGE CHOP / HIGH FRICTION)"),
    };

    let conf_pct = (snap.confidence * 100.0).clamp(0.0, 100.0);
    let conf_bar_len = ((conf_pct / 100.0) * 16.0) as usize;
    let conf_fill = "█".repeat(conf_bar_len);
    let conf_empty = "░".repeat(16 - conf_bar_len);

    // SRS_TUI_EC14: Price Delta Ticker
    let prev_price = if app.current_index > 0 {
        app.snapshots[app.current_index - 1].price
    } else {
        snap.price
    };
    let price_diff = snap.price - prev_price;
    let bps_delta = if prev_price > 0.0 {
        (price_diff / prev_price) * 10_000.0
    } else {
        0.0
    };
    let (ticker_str, ticker_style) = if bps_delta > 0.0 {
        (format!("▲ +{:.1} bps", bps_delta), app.theme.bull)
    } else if bps_delta < 0.0 {
        (format!("▼ {:.1} bps", bps_delta), app.theme.bear)
    } else {
        ("· 0.0 bps".into(), app.theme.muted)
    };

    let banner_text = vec![
        Line::from(vec![Span::styled(state_label, state_style)]),
        Line::from(vec![
            Span::raw("HTF Regime Lock: "),
            Span::styled("15m (3x-15x Filter)", app.theme.gold),
            Span::raw(" │ Active HTF Trend: "),
            Span::styled(
                format!("15m [{}]", snap.trend_15m),
                if snap.trend_15m == "BULL" {
                    app.theme.bull
                } else if snap.trend_15m == "BEAR" {
                    app.theme.bear
                } else {
                    app.theme.chop
                },
            ),
        ]),
        Line::from(vec![
            Span::raw("Model Conviction: "),
            Span::styled(
                format!("[{}{}] {:.1}%", conf_fill, conf_empty, conf_pct),
                app.theme.cyan,
            ),
        ]),
        Line::from(vec![
            Span::raw("Mark Price: "),
            Span::styled(format!("${:.2}", snap.price), app.theme.gold),
            Span::raw(" "),
            Span::styled(ticker_str, ticker_style),
            Span::raw(" │ High: "),
            Span::styled(format!("${:.2}", snap.high), app.theme.bull),
            Span::raw(" │ Low: "),
            Span::styled(format!("${:.2}", snap.low), app.theme.bear),
        ]),
        Line::from(vec![
            Span::raw("Timestamp: "),
            Span::styled(
                format_timestamp_display(&snap.timestamp_str),
                app.theme.muted,
            ),
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

    f.render_widget(
        Paragraph::new(banner_text).block(banner_block),
        top_chunks[0],
    );

    // SRS_TUI_EC13: MTF Hysteresis Matrix with state dots & explicit HTF Lock
    let mtf_text = vec![
        Line::from(vec![
            Span::styled(
                "● ",
                if snap.trend_1m == "BULL" {
                    app.theme.bull
                } else if snap.trend_1m == "BEAR" {
                    app.theme.bear
                } else {
                    app.theme.chop
                },
            ),
            Span::raw(" 1m Trend: "),
            Span::styled(format!(" [{}] ", snap.trend_1m), app.theme.title),
            Span::styled("LTF Execution", app.theme.muted),
        ]),
        Line::from(vec![
            Span::styled(
                "● ",
                if snap.trend_5m == "BULL" {
                    app.theme.bull
                } else if snap.trend_5m == "BEAR" {
                    app.theme.bear
                } else {
                    app.theme.chop
                },
            ),
            Span::raw(" 5m Trend: "),
            Span::styled(format!(" [{}] ", snap.trend_5m), app.theme.title),
            Span::styled("ZLEMA Hysteresis", app.theme.muted),
        ]),
        Line::from(vec![
            Span::styled("★ ", app.theme.gold),
            Span::styled("15m HTF Lock: ", app.theme.gold),
            Span::styled(
                format!(" [{}] ", snap.trend_15m),
                if snap.trend_15m == "BULL" {
                    app.theme.bull
                } else if snap.trend_15m == "BEAR" {
                    app.theme.bear
                } else {
                    app.theme.chop
                },
            ),
            Span::styled("[MACRO REGIME LOCK]", app.theme.title),
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

    // SRS_TUI_EC7: Backend-published microstructure and funding telemetry
    let opi_bipolar = render_bipolar_str(snap.opi, 1.0, "OPI");
    let funding = app
        .backend
        .funding_rate_hourly
        .map(|rate| format!("{:+.6}% / hour", rate * 100.0))
        .unwrap_or_else(|| "not reported".into());

    let micro_text = vec![
        Line::from(vec![
            Span::raw("OPI Order Flow: "),
            Span::styled(
                format!("({:+.2}) ", snap.opi),
                if snap.opi >= 0.0 {
                    app.theme.bull
                } else {
                    app.theme.bear
                },
            ),
            Span::styled(opi_bipolar, app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("Funding Rate: "),
            Span::styled(funding, app.theme.carry),
        ]),
        Line::from(vec![
            Span::raw("Friction Spread: "),
            Span::styled(format!("{:.1} bps ", snap.spread_bps), app.theme.title),
            Span::styled(
                if snap.spread_bps > 6.0 {
                    "[HIGH FRICTION]"
                } else {
                    "[PASS]"
                },
                if snap.spread_bps > 6.0 {
                    app.theme.chop
                } else {
                    app.theme.bull
                },
            ),
        ]),
        Line::from(vec![
            Span::raw("Orderbook Depth: "),
            Span::styled(
                format!("{:.2}x Ratio ", snap.bid_depth_ratio),
                app.theme.gold,
            ),
            Span::styled(
                if snap.bid_depth_ratio >= 1.0 {
                    "(Bids Dominant)"
                } else {
                    "(Asks Dominant)"
                },
                app.theme.muted,
            ),
        ]),
    ];

    let micro_block = Block::default()
        .title(" MICROSTRUCTURE TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(micro_text).block(micro_block), top_chunks[2]);

    // 2. Real-time Price Action Range & Impulse Conviction Telemetry Panel
    let count = app.snapshots.len();
    let start = if app.current_index > 60 {
        app.current_index - 60
    } else {
        0
    };
    let end = (app.current_index + 1).min(count);
    let view_snaps = &app.snapshots[start..end];

    let min_p = view_snaps.iter().map(|s| s.low).fold(f64::MAX, f64::min);
    let max_p = view_snaps.iter().map(|s| s.high).fold(f64::MIN, f64::max);
    let px_pct = if max_p > min_p {
        ((snap.price - min_p) / (max_p - min_p) * 100.0).clamp(0.0, 100.0)
    } else {
        50.0
    };

    let px_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(50), // Price Range & High/Low Trajectory Gauge
            Constraint::Percentage(50), // Volatility & Impulse Conviction Scale
        ])
        .split(main_chunks[1]);

    let px_gauge = Gauge::default()
        .block(
            Block::default()
                .title(format!(
                    " 60-BAR PRICE ACTION RANGE TRAJECTORY (${:.2} -> ${:.2}) ",
                    min_p, max_p
                ))
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .gauge_style(app.theme.gold)
        .percent(px_pct as u16)
        .label(format!(
            "Mark: ${:.2} (60-Bar Range Pos: {:.1}%)",
            snap.price, px_pct
        ));

    f.render_widget(px_gauge, px_chunks[0]);

    let conv_pct = (snap.confidence * 100.0).clamp(0.0, 100.0);
    let conv_gauge = Gauge::default()
        .block(
            Block::default()
                .title(format!(
                    " IMPULSE CONVICTION & DYNAMIC LEVERAGE ENGINE ({:.1}%) ",
                    conv_pct
                ))
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .gauge_style(if snap.confidence >= 0.70 {
            app.theme.bull
        } else {
            app.theme.coiling
        })
        .percent(conv_pct as u16)
        .label(format!(
            "Conviction: {:.1}% │ Dyn Lev: {:.2}x / {:.1}x",
            conv_pct, snap.dynamic_leverage, snap.max_leverage
        ));

    f.render_widget(conv_gauge, px_chunks[1]);

    // 3. Visual Graphics Row (Orderbook BarChart + Regime Histogram BarChart)
    let graphic_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(50), // L2 Orderbook Liquidity Depth BarChart
            Constraint::Percentage(50), // 5-State Regime Distribution BarChart
        ])
        .split(main_chunks[2]);

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
        (
            "TREND_UP",
            if snap.state == RegimeState::BullMomentum {
                90
            } else {
                30
            },
        ),
        (
            "TREND_DOWN",
            if snap.state == RegimeState::BearMomentum {
                90
            } else {
                20
            },
        ),
        (
            "BREAKOUT",
            if snap.state == RegimeState::VolatilityCoiling {
                90
            } else {
                15
            },
        ),
        (
            "TRANSITION",
            if snap.state == RegimeState::FundingCarry {
                90
            } else {
                25
            },
        ),
        (
            "RANGE",
            if snap.state == RegimeState::RangeChop {
                90
            } else {
                40
            },
        ),
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

    // 4. Trajectory & Volatility Compression Sparklines
    let sparkline_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(main_chunks[3]);

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
                    if snap.bbwp_percentile < 20.0 {
                        "[COILING EXTREME]"
                    } else {
                        ""
                    }
                ))
                .title_style(app.theme.gold)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&bbwps)
        .style(if snap.bbwp_percentile < 20.0 {
            app.theme.coiling
        } else {
            app.theme.cyan
        });

    f.render_widget(sparkline_bbwp, sparkline_chunks[1]);

    // 5. SRS_TUI_EC8: Regime Distribution Bar
    render_distribution_bar(f, app, main_chunks[4]);

    // 6. Compact Reserved 5-Row Transition Audit Log Table
    render_event_log(f, app, main_chunks[5]);
}

// SRS_TUI_EC7 Helper: Bipolar center-zero meter string
fn render_bipolar_str(val: f64, max_val: f64, _label: &str) -> String {
    let width = 10;
    let norm = (val / max_val).clamp(-1.0, 1.0);
    let center = width / 2;
    let offset = (norm * (center as f64)).round() as i32;

    let mut chars = vec!['─'; width];
    chars[center] = '│';

    if offset > 0 {
        for i in (center + 1)..=(center + offset as usize).min(width - 1) {
            chars[i] = '█';
        }
    } else if offset < 0 {
        let left_idx = (center as i32 + offset).max(0) as usize;
        for i in left_idx..center {
            chars[i] = '█';
        }
    }
    format!("[{}]", chars.into_iter().collect::<String>())
}

// SRS_TUI_EC8: Horizontal State Distribution Bar
fn render_distribution_bar(f: &mut Frame, app: &App, area: Rect) {
    if area.width < 10 || app.snapshots.is_empty() {
        return;
    }
    let [bull_cnt, bear_cnt, coil_cnt, carry_cnt, chop_cnt] = distribution_counts(app);
    let total = f64::max(bull_cnt + bear_cnt + coil_cnt + carry_cnt + chop_cnt, 1.0);
    let bull_pct = (bull_cnt / total) * 100.0;
    let bear_pct = (bear_cnt / total) * 100.0;
    let coil_pct = (coil_cnt / total) * 100.0;
    let carry_pct = (carry_cnt / total) * 100.0;
    let chop_pct = (chop_cnt / total) * 100.0;

    let line = Line::from(vec![
        Span::styled(
            format!("TRANSITION DISTRIBUTION: TREND_UP {:.0}% ", bull_pct),
            app.theme.bull,
        ),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("TREND_DOWN {:.0}% ", bear_pct), app.theme.bear),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("BREAKOUT {:.0}% ", coil_pct), app.theme.coiling),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("TRANSITION {:.0}% ", carry_pct), app.theme.carry),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("RANGE {:.0}%", chop_pct), app.theme.chop),
    ]);

    f.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

fn distribution_counts(app: &App) -> [f64; 5] {
    if !app.backend.regime_history.is_empty() {
        let mut counts = [0.0; 5];
        for regime in &app.backend.regime_history {
            let index = match regime.as_str() {
                "TREND_UP" => 0,
                "TREND_DOWN" => 1,
                "BREAKOUT" => 2,
                "TRANSITION" => 3,
                _ => 4,
            };
            counts[index] += 1.0;
        }
        return counts;
    }
    let current_ts = &app.current_snapshot().timestamp_str;
    let states: Vec<RegimeState> = app
        .events
        .iter()
        .filter(|event| &event.timestamp_str <= current_ts)
        .map(|event| event.to_state)
        .collect();
    if states.is_empty() {
        return counts_for_states(&[app.current_snapshot().state]);
    }
    counts_for_states(&states)
}

fn counts_for_states(states: &[RegimeState]) -> [f64; 5] {
    let mut counts = [0.0; 5];
    for state in states {
        let index = match state {
            RegimeState::BullMomentum => 0,
            RegimeState::BearMomentum => 1,
            RegimeState::VolatilityCoiling => 2,
            RegimeState::FundingCarry => 3,
            RegimeState::RangeChop => 4,
        };
        counts[index] += 1.0;
    }
    counts
}

// ============================================================================
// SCREEN 1: DASHBOARD (STRATEGY POLICY & RISK ALLOCATION)
// ============================================================================
fn render_screen_strategy_policy(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6), // Row 1: Strategy Command Box (42%) + Dynamic Leverage Panel (58%)
            Constraint::Length(4), // Row 2: Loaded Strategy Portfolio Matrix (Hypervelocity Only)
            Constraint::Length(10), // Row 3: Active Position Telemetry + L2 Depth Ladder Stack
            Constraint::Length(6), // Row 4: Performance Summary Section
            Constraint::Min(6),    // Row 5: Paper Trade Journal Log (60%) + Trend State Log (40%)
        ])
        .split(area);

    // Row 1: Narrower Strategy Command Box + Dynamic Leverage Panel
    let row1_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(42), Constraint::Percentage(58)])
        .split(main_chunks[0]);

    hypervelocity::render_command_bar(f, app, row1_chunks[0]);
    render_dynamic_leverage_panel(f, app, row1_chunks[1]);

    // Row 2: Loaded Strategy Matrix (Hypervelocity Only)
    render_registered_strategy_matrix(f, app, main_chunks[1]);

    // Row 3: Active Position Telemetry + Orderbook L2 Depth Ladder
    hypervelocity::render_position_and_book(f, app, main_chunks[2]);

    // Row 4: Performance Summary Section
    render_bottom_performance_section(f, app, main_chunks[3]);

    // Row 5: Transition Distribution mirror + full-width Paper Trade Journal
    render_bottom_journal_and_trend_log(f, app, main_chunks[4]);
}

fn render_bottom_performance_section(f: &mut Frame, app: &App, area: Rect) {
    let perf_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(34), // Dedicated Account Portfolio & Margin Telemetry Box (First)
            Constraint::Percentage(33), // All-Time Performance Summary Box
            Constraint::Percentage(33), // This Run Performance Box
        ])
        .split(area);

    render_screen3_portfolio_telemetry_box(f, app, perf_chunks[0]);
    hypervelocity::render_all_time_stats(f, app, perf_chunks[1]);
    hypervelocity::render_run_stats(f, app, perf_chunks[2]);
}

fn render_screen3_portfolio_telemetry_box(f: &mut Frame, app: &App, area: Rect) {
    let stats = &app.paper_stats;
    let net_pnl = stats.current_equity - stats.initial_capital;
    let pnl_style = if net_pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let eq_pct = (stats.current_equity - stats.initial_capital) / stats.initial_capital * 100.0;

    let text = vec![
        Line::from(vec![
            Span::raw("INITIAL CAP: "),
            Span::styled(format!("${:.2}", stats.initial_capital), app.theme.title),
            Span::raw("  EQUITY: "),
            Span::styled(
                format!("${:.2} ({:+.2}%)", stats.current_equity, eq_pct),
                pnl_style,
            ),
        ]),
        Line::from(vec![
            Span::raw("NET PNL:     "),
            Span::styled(format!("{:+.2} USD", normalized_zero(net_pnl)), pnl_style),
            Span::raw("  MARGIN: "),
            Span::styled(portfolio_margin_display(app), app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("EXECUTION:   "),
            Span::styled(execution_display(app), app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("TOTAL TRADES: "),
            Span::styled(format!("{}", stats.total_trades), app.theme.gold),
            Span::raw("  WIN RATE: "),
            Span::styled(
                format!(
                    "{:.1}% ({}W/{}L)",
                    stats.win_rate_pct, stats.wins, stats.losses
                ),
                if stats.win_rate_pct >= 50.0 {
                    app.theme.bull
                } else {
                    app.theme.bear
                },
            ),
        ]),
    ];

    let block = Block::default()
        .title(" SHADOW PORTFOLIO TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(text).block(block), area);
}

fn portfolio_margin_display(app: &App) -> String {
    let Some(fraction) = backend_f64(&app.backend.risk, "margin_fraction") else {
        return "not reported".to_string();
    };
    let allocated = if app.active_position.is_active() && app.active_position.leverage > 0.0 {
        app.active_position.entry_price * app.active_position.size_btc
            / app.active_position.leverage
    } else {
        app.paper_stats.current_equity * fraction
    };
    format!("${allocated:.2} ({:.0}% Alloc)", fraction * 100.0)
}

fn execution_display(app: &App) -> String {
    let mode = app
        .backend
        .execution_mode
        .as_deref()
        .unwrap_or("not reported")
        .to_uppercase();
    let time_in_force = app
        .backend
        .execution_policy
        .get("time_in_force")
        .and_then(serde_json::Value::as_str);
    let maker_fee = backend_f64(&app.backend.costs, "maker_fee_rate");
    match (time_in_force, maker_fee) {
        (Some("post_only"), Some(fee)) => {
            format!("{mode} | POST-ONLY MAKER | {:.2}bps/side", fee * 10_000.0)
        }
        _ => format!("{mode} | backend execution costs not reported"),
    }
}

fn backend_f64(value: &serde_json::Value, key: &str) -> Option<f64> {
    value.get(key).and_then(serde_json::Value::as_f64)
}

fn normalized_zero(value: f64) -> f64 {
    if value.abs() < 0.005 { 0.0 } else { value }
}

fn render_bottom_journal_and_trend_log(f: &mut Frame, app: &App, area: Rect) {
    let row5_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Transition Distribution line (mirrored from Screen 1)
            Constraint::Min(4),    // Full-width Live Paper Trade Journal Log Table
        ])
        .split(area);

    render_distribution_bar(f, app, row5_chunks[0]);
    render_paper_journal_log(f, app, row5_chunks[1]);
}

fn render_dynamic_leverage_panel(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let stats = &app.paper_stats;

    let lev_pct = ((snap.dynamic_leverage / snap.max_leverage) * 100.0).clamp(0.0, 100.0);
    let lev_bar_len = ((lev_pct / 100.0) * 12.0) as usize;
    let lev_fill = "█".repeat(lev_bar_len);
    let lev_empty = "░".repeat(12 - lev_bar_len);

    let lw_pct = (snap.long_weight / 2.0).clamp(0.0, 1.0);
    let lw_len = (lw_pct * 10.0) as usize;
    let lw_fill = "█".repeat(lw_len);
    let lw_empty = "░".repeat(10 - lw_len);

    let sw_pct = (snap.short_weight / 2.0).clamp(0.0, 1.0);
    let sw_len = (sw_pct * 10.0) as usize;
    let sw_fill = "█".repeat(sw_len);
    let sw_empty = "░".repeat(10 - sw_len);

    let net_weight = snap.long_weight - snap.short_weight;
    let (net_str, net_style) = if net_weight > 0.0 {
        (format!("+{:.2}x NET LONG", net_weight), app.theme.bull)
    } else if net_weight < 0.0 {
        (format!("{:.2}x NET SHORT", net_weight), app.theme.bear)
    } else {
        ("0.00x FLAT".into(), app.theme.gold)
    };

    let pnl_sign = if stats.realized_pnl >= 0.0 { "+" } else { "" };
    let pnl_style = if stats.realized_pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };

    let policy_text = vec![
        Line::from(vec![
            Span::raw("Dynamic Leverage: "),
            Span::styled(
                format!(
                    "[{}{}] {:.2}x / {:.1}x",
                    lev_fill, lev_empty, snap.dynamic_leverage, snap.max_leverage
                ),
                app.theme.gold,
            ),
            Span::raw(" │ Net Position: "),
            Span::styled(net_str, net_style),
        ]),
        Line::from(vec![
            Span::raw("Long Alloc: "),
            Span::styled(
                format!("[{}{}] {:.2}x", lw_fill, lw_empty, snap.long_weight),
                app.theme.bull,
            ),
            Span::raw(" │ Short Alloc: "),
            Span::styled(
                format!("[{}{}] {:.2}x", sw_fill, sw_empty, snap.short_weight),
                app.theme.bear,
            ),
        ]),
        Line::from(vec![
            Span::raw("OPI Flow: "),
            Span::styled(
                format!("({:+.2}) ", snap.opi),
                if snap.opi >= 0.0 {
                    app.theme.bull
                } else {
                    app.theme.bear
                },
            ),
            Span::styled(
                if snap.opi >= 0.0 {
                    "BULLISH_FLOW"
                } else {
                    "BEARISH_FLOW"
                },
                app.theme.cyan,
            ),
            Span::raw(" │ Funding Z: "),
            Span::styled(format!("{:.2}", snap.funding_zscore), app.theme.carry),
            Span::raw(" │ RSI (14): "),
            Span::styled(format!("{:.1}", snap.rsi), app.theme.cyan),
        ]),
        Line::from(vec![
            Span::raw("Account: "),
            Span::raw("Equity "),
            Span::styled(format!("${:.2}", stats.current_equity), app.theme.title),
            Span::raw(" │ PnL "),
            Span::styled(format!("{}{:.2}", pnl_sign, stats.realized_pnl), pnl_style),
            Span::raw(" │ Execution: "),
            Span::styled(
                if snap.taker_allowed {
                    "TAKERS PERMITTED"
                } else {
                    "MAKER ONLY"
                },
                if snap.taker_allowed {
                    app.theme.bull
                } else {
                    app.theme.gold
                },
            ),
        ]),
    ];

    let policy_block = Block::default()
        .title(" DYNAMIC LEVERAGE & NET POSITION SIZING ENGINE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);

    f.render_widget(Paragraph::new(policy_text).block(policy_block), area);
}

fn render_registered_strategy_matrix(f: &mut Frame, app: &App, area: Rect) {
    let backend_state = match app.backend.connection {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    };
    let strategy = app.backend.strategy_name.as_deref().unwrap_or("unknown");
    let model_probability = app
        .backend
        .latest_metalabel_p
        .map(|value| format!("{value:.4}"))
        .unwrap_or_else(|| "n/a".to_string());
    let leverage = app
        .backend
        .strategy_params
        .get("leverage")
        .and_then(serde_json::Value::as_f64)
        .map(|value| format!("{value:.1}x"))
        .unwrap_or_else(|| "n/a".to_string());
    let model_mode = app.backend.metalabel_mode.as_deref().unwrap_or("off");
    let strategy_rows = vec![Row::new(vec![
        Span::styled(strategy, app.theme.gold),
        Span::styled(backend_state, app.theme.cyan),
        Span::styled(model_probability, app.theme.gold),
        Span::styled(leverage, app.theme.cyan),
        Span::styled(
            format!(
                "run={} | execution={} | metalabel={}",
                app.backend.run_id.as_deref().unwrap_or("unknown"),
                app.backend.execution_mode.as_deref().unwrap_or("unknown"),
                model_mode,
            ),
            app.theme.title,
        ),
    ])];

    let strategy_table = Table::new(
        strategy_rows,
        [
            Constraint::Length(26),
            Constraint::Length(20),
            Constraint::Length(14),
            Constraint::Length(14),
            Constraint::Min(30),
        ],
    )
    .header(Row::new(
        [
            "Backend Strategy",
            "Telemetry",
            "Model p",
            "Leverage",
            "Authoritative Run Identity",
        ]
        .iter()
        .map(|h| Span::styled(*h, app.theme.header)),
    ))
    .block(
        Block::default()
            .title(" BACKEND STRATEGY EXECUTION TELEMETRY ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(strategy_table, area);
}

fn render_event_log(f: &mut Frame, app: &App, area: Rect) {
    let header_cells = [
        "Timestamp",
        "From State",
        "To State",
        "Price",
        "Trigger Diagnostic",
    ]
    .iter()
    .map(|h| Span::styled(*h, app.theme.header));
    let header = Row::new(header_cells).height(1);

    let current_ts = &app.current_snapshot().timestamp_str;
    let max_rows = area.height.saturating_sub(3).max(5) as usize;
    let recent_events: Vec<_> = app
        .events
        .iter()
        .filter(|e| &e.timestamp_str <= current_ts)
        .rev()
        .take(max_rows)
        .collect();
    let mut rows: Vec<Row> = recent_events
        .iter()
        .enumerate()
        .map(|(idx, ev)| {
            let from_str = ev.from_state.display_name();
            let to_str = ev.to_state.display_name();
            let is_selected = idx
                == app
                    .selected_event_index
                    .min(recent_events.len().saturating_sub(1));

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

            let row_style = if is_selected {
                app.theme.highlight
            } else {
                ratatui::style::Style::default()
            };
            let ts_display = format_timestamp_display(&ev.timestamp_str);

            Row::new(vec![
                Span::styled(
                    ts_display,
                    if is_selected {
                        app.theme.highlight
                    } else {
                        app.theme.muted
                    },
                ),
                Span::styled(from_str, row_style),
                Span::styled(to_str, to_style),
                Span::styled(
                    format!("${:.2}", ev.price),
                    if is_selected {
                        app.theme.highlight
                    } else {
                        app.theme.gold
                    },
                ),
                Span::styled(
                    &ev.trigger_reason,
                    if is_selected {
                        app.theme.highlight
                    } else {
                        app.theme.cyan
                    },
                ),
            ])
            .style(row_style)
        })
        .collect();
    if rows.is_empty() {
        rows.push(Row::new(vec![
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
        ]));
    }
    let selected_position = if recent_events.is_empty() {
        0
    } else {
        app.selected_event_index.min(recent_events.len() - 1) + 1
    };

    let table = Table::new(
        rows,
        [
            Constraint::Length(19),
            Constraint::Length(40),
            Constraint::Length(40),
            Constraint::Length(12),
            Constraint::Min(25),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(
                " RECENT REGIME TRANSITION AUDIT LOG (Use [↑/↓] or [j/k] to navigate, [Enter] for details) [{}/{}] ",
                selected_position,
                recent_events.len()
            ))
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(table, area);
}

fn render_paper_journal_log(f: &mut Frame, app: &App, area: Rect) {
    let header_cells = [
        "Trade ID",
        "Timestamp",
        "Direction",
        "Entry Price",
        "Exit Price",
        "Size (BTC)",
        "Leverage",
        "Realized PnL",
        "Exit Trigger",
    ]
    .iter()
    .map(|h| Span::styled(*h, app.theme.header));
    let header = Row::new(header_cells).height(1);

    let max_rows = area.height.saturating_sub(3).max(1) as usize;
    let open_count = usize::from(app.active_position.is_active());
    let closed_limit = max_rows.saturating_sub(open_count);
    let recent_trades: Vec<_> = app.paper_trades.iter().rev().take(closed_limit).collect();
    let mut rows = Vec::with_capacity(recent_trades.len() + open_count);
    if app.active_position.is_active() {
        let position = &app.active_position;
        let direction_style = if position.direction == "LONG" {
            app.theme.bull
        } else {
            app.theme.bear
        };
        rows.push(Row::new(vec![
            Span::styled("OPEN", app.theme.gold),
            Span::styled(
                format_timestamp_display(&position.entry_timestamp),
                app.theme.muted,
            ),
            Span::styled(&position.direction, direction_style),
            Span::styled(format!("${:.2}", position.entry_price), app.theme.title),
            Span::styled("OPEN", app.theme.cyan),
            Span::styled(format!("{:.4}", position.size_btc), app.theme.cyan),
            Span::styled(format!("{:.1}x", position.leverage), app.theme.gold),
            Span::styled(
                format!(
                    "UNREAL {:+.2}",
                    normalized_zero(app.paper_stats.unrealized_pnl)
                ),
                if app.paper_stats.unrealized_pnl >= 0.0 {
                    app.theme.bull
                } else {
                    app.theme.bear
                },
            ),
            Span::styled("AWAITING TP", app.theme.gold),
        ]));
    }
    rows.extend(recent_trades.iter().map(|trd| {
        let dir_style = if trd.direction == "LONG" {
            app.theme.bull
        } else {
            app.theme.bear
        };
        let (pnl_sign, pnl_color) = if trd.pnl_usd >= 0.0 {
            ("+", app.theme.bull)
        } else {
            ("", app.theme.bear)
        };

        let ts_display = format_timestamp_display(&trd.timestamp_str);

        Row::new(vec![
            Span::styled(&trd.trade_id, app.theme.gold),
            Span::styled(ts_display, app.theme.muted),
            Span::styled(&trd.direction, dir_style),
            Span::styled(format!("${:.2}", trd.entry_price), app.theme.title),
            Span::styled(format!("${:.2}", trd.exit_price), app.theme.title),
            Span::styled(format!("{:.4}", trd.size_btc), app.theme.cyan),
            Span::styled(format!("{:.1}x", trd.leverage), app.theme.gold),
            Span::styled(
                format!(
                    "{}{:.2} ({}{:.2}%)",
                    pnl_sign, trd.pnl_usd, pnl_sign, trd.pnl_pct
                ),
                pnl_color,
            ),
            Span::styled(&trd.exit_reason, app.theme.muted),
        ])
    }));

    let table = Table::new(
        rows,
        [
            Constraint::Length(8),
            Constraint::Length(19),
            Constraint::Length(7),
            Constraint::Length(11),
            Constraint::Length(11),
            Constraint::Length(10),
            Constraint::Length(7),
            Constraint::Length(18),
            Constraint::Min(12),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(
                " LIVE PAPER JOURNAL (CLOSED TRADES: {} | OPEN POSITIONS: {}) ",
                app.paper_trades.len(),
                open_count
            ))
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );

    f.render_widget(table, area);
}

fn render_footer(f: &mut Frame, app: &App, area: Rect) {
    if app.active_tab == 2 {
        let rows = crate::config_view::backend_config_rows(&app.backend);
        let selected = if rows.is_empty() {
            0
        } else {
            app.config.selected_option_index.min(rows.len() - 1) + 1
        };
        let line = Line::from(vec![
            Span::styled("[Tab / 1-3]", app.theme.gold),
            Span::raw(" Switch Screen │ "),
            Span::styled("[↑/↓ j/k]", app.theme.gold),
            Span::raw(" Select Option │ "),
            Span::styled("[q]", app.theme.gold),
            Span::raw(" Quit │ "),
            Span::styled(format!("Option {selected}/{}", rows.len()), app.theme.cyan),
            Span::raw(" │ BACKEND READ ONLY"),
        ]);
        f.render_widget(
            Paragraph::new(line)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_style(app.theme.border),
                )
                .alignment(Alignment::Center),
            area,
        );
        return;
    }
    let total = app.snapshots.len();
    let current = app.current_index + 1;
    let scrub_pct = ((current as f64 / total as f64) * 100.0).clamp(0.0, 100.0);
    let bar_len = ((scrub_pct / 100.0) * 16.0) as usize;
    let fill = "█".repeat(bar_len);
    let empty = "░".repeat(16 - bar_len);

    let help_text = Line::from(vec![
        Span::styled("[Tab / 1-3]", app.theme.gold),
        Span::raw(" Switch Screen View │ "),
        Span::styled("[Space]", app.theme.gold),
        Span::raw(" Play/Pause │ "),
        Span::styled("[←/→]", app.theme.gold),
        Span::raw(" Scrub │ "),
        Span::styled("[↑/↓ j/k]", app.theme.gold),
        Span::raw(" Select Event │ "),
        Span::styled("[Enter]", app.theme.gold),
        Span::raw(" Details │ "),
        Span::styled("[?]", app.theme.gold),
        Span::raw(" Help │ "),
        Span::styled("Scrub: ", app.theme.cyan),
        Span::styled(
            format!(
                "[{}{}] {:.1}% ({}/{})",
                fill, empty, scrub_pct, current, total
            ),
            app.theme.title,
        ),
    ]);

    let p = Paragraph::new(help_text)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
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
        Line::from(vec![Span::styled(
            "🔬 TRANSITION DIAGNOSTIC INSPECTOR",
            app.theme.title,
        )]),
        Line::from(vec![Span::styled(
            "────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![
            Span::raw("Timestamp:           "),
            Span::styled(format_timestamp_display(&ev.timestamp_str), app.theme.muted),
        ]),
        Line::from(vec![
            Span::raw("Origin State:        "),
            Span::styled(ev.from_state.display_name(), app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("Destination State:   "),
            Span::styled(ev.to_state.display_name(), app.theme.bull),
        ]),
        Line::from(vec![
            Span::raw("Transition Price:    "),
            Span::styled(format!("${:.2}", ev.price), app.theme.gold),
        ]),
        Line::from(vec![Span::styled(
            "────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![Span::styled(
            "TRIGGER DIAGNOSTIC REASON:",
            app.theme.cyan,
        )]),
        Line::from(vec![Span::styled(
            format!("  \"{}\"", ev.trigger_reason),
            app.theme.title,
        )]),
        Line::from(vec![Span::styled(
            "────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![Span::styled(
            "Press [Enter] or [Esc] to return to Cockpit View",
            app.theme.muted,
        )]),
    ];

    let block = Block::default()
        .title(" EVENT DIAGNOSTIC INSPECTOR ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(lines)
        .block(block)
        .alignment(Alignment::Left);
    f.render_widget(p, modal_area);
}

fn render_help_overlay(f: &mut Frame, app: &App, area: Rect) {
    let modal_area = centered_rect(65, 75, area);
    f.render_widget(Clear, modal_area);

    let lines = vec![
        Line::from(vec![Span::styled(
            "⚡ HYPERVECTOR ULTIMATE REGIME ENGINE RULES & KEYBINDINGS",
            app.theme.title,
        )]),
        Line::from(vec![Span::styled(
            "───────────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![Span::styled(
            "🏛️ 5-TIER MICROSTRUCTURE REGIME CLASSIFICATION RULES:",
            app.theme.gold,
        )]),
        Line::from(vec![Span::styled(
            "  🔥 TREND_UP       : 15m/5m Bull MTF + ADX > 25 + OPI >= 0.0",
            app.theme.bull,
        )]),
        Line::from(vec![Span::styled(
            "  🔻 TREND_DOWN     : 15m/5m Bear MTF + ADX > 25 + OPI <= 0.0",
            app.theme.bear,
        )]),
        Line::from(vec![Span::styled(
            "  ⚡ BREAKOUT       : BBWP Compression Percentile < 20.0 (Coiling)",
            app.theme.coiling,
        )]),
        Line::from(vec![Span::styled(
            "  💰 TRANSITION     : Funding Rate Z-Score |Z| >= 1.8 (Carry Reversal)",
            app.theme.carry,
        )]),
        Line::from(vec![Span::styled(
            "  🛡️ RANGE          : Choppiness Index > 55 or Spread > 6.0 bps",
            app.theme.chop,
        )]),
        Line::from(vec![Span::styled(
            "───────────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![Span::styled(
            "📊 DYNAMIC LEVERAGE SCALING (HYPERTRADER 1M IMPULSE ML):",
            app.theme.gold,
        )]),
        Line::from(vec![Span::raw(
            "  L_dynamic = clamp(L_cap * conviction * (1 + |OPI| * 0.5), 1.0, L_cap)",
        )]),
        Line::from(vec![Span::styled(
            "───────────────────────────────────────────────────────────────────",
            app.theme.border,
        )]),
        Line::from(vec![Span::styled(
            "⌨️ INTERACTIVE KEYBOARD CONTROLS:",
            app.theme.cyan,
        )]),
        Line::from(vec![
            Span::styled("  [Tab / 1-3]   ", app.theme.gold),
            Span::raw("Switch View Screen (1: Regime Engine, 2: Dashboard, 3: Config)"),
        ]),
        Line::from(vec![
            Span::styled("  [Space]       ", app.theme.gold),
            Span::raw("Toggle Play / Pause Real-time Stream"),
        ]),
        Line::from(vec![
            Span::styled("  [← / →]       ", app.theme.gold),
            Span::raw("Step Backwards / Forwards through History"),
        ]),
        Line::from(vec![
            Span::styled("  [↑ / ↓ j/k]   ", app.theme.gold),
            Span::raw("Navigate Recent Transition Event Rows"),
        ]),
        Line::from(vec![
            Span::styled("  [Enter]       ", app.theme.gold),
            Span::raw("Open Transition Event Diagnostic Inspector Modal"),
        ]),
        Line::from(vec![
            Span::styled("  [s]           ", app.theme.gold),
            Span::raw("Cycle Playback Speed (1.0x -> 2.0x -> 5.0x -> 10.0x)"),
        ]),
        Line::from(vec![
            Span::styled("  [t]           ", app.theme.gold),
            Span::raw("Cycle Timeframe (1m -> 5m -> 15m)"),
        ]),
        Line::from(vec![
            Span::styled("  [r]           ", app.theme.gold),
            Span::raw("Reset Scrub Position to Start"),
        ]),
        Line::from(vec![
            Span::styled("  [? / h]       ", app.theme.gold),
            Span::raw("Toggle this Help & Rules Overlay Window"),
        ]),
        Line::from(vec![
            Span::styled("  [q / Esc]     ", app.theme.gold),
            Span::raw("Dismiss Overlay / Quit Cockpit"),
        ]),
    ];

    let block = Block::default()
        .title(" COCKPIT HELP & ENGINE ARCHITECTURE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active);

    let p = Paragraph::new(lines)
        .block(block)
        .alignment(Alignment::Left);
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
