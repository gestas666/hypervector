//! Regime-detection screen composition and graphical panels.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{BarChart, Block, BorderType, Borders, Gauge, Paragraph, Sparkline},
};

use super::{logs, regime_widgets as widgets, time::format_timestamp_display};
use crate::{app::App, model::RegimeSnapshot};

pub(super) fn render(f: &mut Frame, app: &App, area: Rect) {
    if render_specialized_screen(f, app, area) {
        return;
    }
    let compact = area.height < 40;
    let heights = if compact {
        [6, 5, 5, 5, 1]
    } else {
        [8, 7, 7, 7, 1]
    };
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(heights[0]),
            Constraint::Length(heights[1]),
            Constraint::Length(heights[2]),
            Constraint::Length(heights[3]),
            Constraint::Length(heights[4]),
            Constraint::Min(if compact { 5 } else { 6 }),
        ])
        .split(area);
    render_top_row(f, app, chunks[0]);
    render_price_strength(f, app, chunks[1]);
    render_graphics(f, app, chunks[2]);
    render_sparklines(f, app, chunks[3]);
    widgets::render_distribution_bar(f, app, chunks[4]);
    logs::render_event_log(f, app, chunks[5]);
}

fn render_specialized_screen(f: &mut Frame, app: &App, area: Rect) -> bool {
    if app.backend.is_apex_mm() {
        crate::apex_mm_view::render_microstructure(f, app, area);
    } else if app.backend.is_pine_stack() {
        crate::pine_stack_view::render_signal_engine(f, app, area);
    } else if app.backend.is_hulk_smash() {
        crate::hulk_smash_view::render_signal_engine(f, app, area);
    } else {
        return false;
    }
    true
}

fn render_top_row(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42),
            Constraint::Percentage(28),
            Constraint::Percentage(30),
        ])
        .split(area);
    render_active_regime(f, app, chunks[0]);
    render_timeframe_matrix(f, app, chunks[1]);
    let block = Block::default()
        .title(" MICROSTRUCTURE TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(
        Paragraph::new(widgets::microstructure_lines(app, app.current_snapshot())).block(block),
        chunks[2],
    );
}

fn render_active_regime(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let state_style = widgets::state_style(app, snap.state);
    let confidence_pct = (snap.confidence * 100.0).clamp(0.0, 100.0);
    let (ticker, ticker_style) = price_ticker(app, snap);
    let lines = if app.backend.is_source_follow() {
        widgets::source_follow_regime_banner(
            app,
            snap,
            snap.state.display_name(),
            confidence_pct,
            &ticker,
            ticker_style,
        )
    } else {
        canonical_regime_banner(app, snap, confidence_pct, &ticker, ticker_style)
    };
    let block = Block::default()
        .title(" ACTIVE MARKET REGIME TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Thick)
        .border_style(state_style);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn price_ticker(app: &App, snap: &RegimeSnapshot) -> (String, Style) {
    let previous = if app.current_index > 0 {
        app.snapshots[app.current_index - 1].price
    } else {
        snap.price
    };
    let bps = if previous > 0.0 {
        (snap.price - previous) / previous * 10_000.0
    } else {
        0.0
    };
    if bps > 0.0 {
        (format!("▲ +{bps:.1} bps"), app.theme.bull)
    } else if bps < 0.0 {
        (format!("▼ {bps:.1} bps"), app.theme.bear)
    } else {
        ("· 0.0 bps".into(), app.theme.muted)
    }
}

fn canonical_regime_banner(
    app: &App,
    snap: &RegimeSnapshot,
    confidence_pct: f64,
    ticker: &str,
    ticker_style: Style,
) -> Vec<Line<'static>> {
    let bar_len = (confidence_pct / 100.0 * 16.0) as usize;
    let context_style = trend_style(app, &snap.trend_15m);
    vec![
        Line::from(Span::styled(
            snap.state.display_name(),
            widgets::state_style(app, snap.state),
        )),
        Line::from(vec![
            Span::raw("Canonical Primary: "),
            Span::styled("5m authoritative", app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("Context Only: "),
            Span::styled(format!("15m [{}]", snap.trend_15m), context_style),
        ]),
        confidence_line(app, confidence_pct, bar_len),
        market_line(app, snap, ticker, ticker_style),
        timestamp_line(app, snap),
    ]
}

fn confidence_line(app: &App, confidence_pct: f64, bar_len: usize) -> Line<'static> {
    Line::from(vec![
        Span::raw("Structure Strength: "),
        Span::styled(
            format!(
                "[{}{}] {confidence_pct:.1}%",
                "█".repeat(bar_len),
                "░".repeat(16 - bar_len)
            ),
            app.theme.cyan,
        ),
    ])
}

fn market_line(app: &App, snap: &RegimeSnapshot, ticker: &str, style: Style) -> Line<'static> {
    Line::from(vec![
        Span::raw("Mark Price: "),
        Span::styled(format!("${:.2}", snap.price), app.theme.gold),
        Span::raw(" "),
        Span::styled(ticker.to_string(), style),
        Span::raw(" │ High: "),
        Span::styled(format!("${:.2}", snap.high), app.theme.bull),
        Span::raw(" │ Low: "),
        Span::styled(format!("${:.2}", snap.low), app.theme.bear),
    ])
}

fn timestamp_line(app: &App, snap: &RegimeSnapshot) -> Line<'static> {
    Line::from(vec![
        Span::raw("Timestamp: "),
        Span::styled(
            format_timestamp_display(&snap.timestamp_str),
            app.theme.muted,
        ),
        Span::raw(" │ Volume: "),
        Span::styled(
            format!("{:.1} {}", snap.volume, app.symbol),
            app.theme.title,
        ),
    ])
}

fn render_timeframe_matrix(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let lines = if app.backend.is_source_follow() {
        widgets::source_follow_timeframe_matrix(app, snap, area)
    } else {
        canonical_timeframe_lines(app, snap)
    };
    let block = Block::default()
        .title(" MTF HYSTERESIS MATRIX ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn canonical_timeframe_lines(app: &App, snap: &RegimeSnapshot) -> Vec<Line<'static>> {
    vec![
        timeframe_line(app, " 1m Trend: ", &snap.trend_1m, "LTF Execution"),
        timeframe_line(app, " 5m PRIMARY: ", &snap.trend_5m, "CANONICAL AUTHORITY"),
        Line::from(vec![
            Span::styled("* ", app.theme.gold),
            Span::styled("15m CONTEXT: ", app.theme.gold),
            Span::styled(
                format!(" [{}] ", snap.trend_15m),
                trend_style(app, &snap.trend_15m),
            ),
            Span::styled("[NON-VETO CONTEXT]", app.theme.title),
        ]),
        Line::from(vec![
            Span::raw("Alignment: "),
            Span::styled(alignment_label(snap), app.theme.title),
        ]),
        Line::from(vec![
            Span::raw("Lookahead Guard: "),
            Span::styled("COMPLETED BARS ONLY", app.theme.bull),
        ]),
    ]
}

fn timeframe_line(
    app: &App,
    label: &'static str,
    trend: &str,
    role: &'static str,
) -> Line<'static> {
    Line::from(vec![
        Span::styled("● ", trend_style(app, trend)),
        Span::raw(label),
        Span::styled(format!(" [{trend}] "), app.theme.title),
        Span::styled(role, app.theme.muted),
    ])
}

fn trend_style(app: &App, trend: &str) -> Style {
    if matches!(trend, "TREND_UP" | "BULL") {
        app.theme.bull
    } else if matches!(trend, "TREND_DOWN" | "BEAR") {
        app.theme.bear
    } else {
        app.theme.chop
    }
}

fn alignment_label(snap: &RegimeSnapshot) -> &'static str {
    if snap.trend_1m == snap.trend_5m && snap.trend_5m == snap.trend_15m {
        "FULL 3-TF ALIGNMENT"
    } else {
        "PARTIAL ALIGNMENT"
    }
}

fn render_price_strength(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    let snap = app.current_snapshot();
    let (minimum, maximum, position) = price_range(app, snap);
    let range = Gauge::default()
        .block(panel_block(
            app,
            format!(" 60B PRICE RANGE ${minimum:.2}-${maximum:.2} "),
            app.theme.bear,
        ))
        .gauge_style(app.theme.bear)
        .percent(position as u16)
        .label(format!(
            "Mark: ${:.2} (60-Bar Range Pos: {position:.1}%)",
            snap.price
        ));
    f.render_widget(range, chunks[0]);
    render_strength_gauge(f, app, chunks[1]);
}

fn price_range(app: &App, snap: &RegimeSnapshot) -> (f64, f64, f64) {
    let start = app.current_index.saturating_sub(60);
    let end = (app.current_index + 1).min(app.snapshots.len());
    let snapshots = &app.snapshots[start..end];
    let minimum = snapshots
        .iter()
        .map(|value| value.low)
        .fold(f64::MAX, f64::min);
    let maximum = snapshots
        .iter()
        .map(|value| value.high)
        .fold(f64::MIN, f64::max);
    let position = if maximum > minimum {
        ((snap.price - minimum) / (maximum - minimum) * 100.0).clamp(0.0, 100.0)
    } else {
        50.0
    };
    (minimum, maximum, position)
}

fn render_strength_gauge(f: &mut Frame, app: &App, area: Rect) {
    let strength = (app.current_snapshot().confidence * 100.0).clamp(0.0, 100.0);
    let (title, label) = if app.backend.is_source_follow() {
        (
            format!(" SOURCE CONFIDENCE {strength:.1}% · ENTRY GATE "),
            format!(
                "Pinned classifier confidence: {strength:.1}% │ Source: {}",
                widgets::compact_regime_score_source(
                    app.backend.latest_regime_score_source.as_deref()
                )
            ),
        )
    } else {
        (
            format!(" REGIME STRENGTH {strength:.1}% · REPORT ONLY "),
            format!(
                "Structure score: {strength:.1}% │ Source: {}",
                widgets::compact_regime_score_source(
                    app.backend.latest_regime_score_source.as_deref()
                )
            ),
        )
    };
    let gauge = Gauge::default()
        .block(panel_block(app, title, app.theme.carry))
        .gauge_style(app.theme.carry)
        .percent(strength as u16)
        .label(label);
    f.render_widget(gauge, area);
}

fn panel_block<'a>(app: &App, title: String, title_style: Style) -> Block<'a> {
    Block::default()
        .title(title)
        .title_style(title_style)
        .borders(Borders::ALL)
        .border_style(app.theme.border)
}

fn render_graphics(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    render_orderbook_chart(f, app, chunks[0]);
    render_distribution_chart(f, app, chunks[1]);
}

fn render_orderbook_chart(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let unavailable = snap.microstructure_source == "not_available";
    let values = if unavailable {
        [0, 0]
    } else {
        [
            (snap.bid_depth_ratio * 100.0) as u64,
            (100.0 / snap.bid_depth_ratio.max(0.1)) as u64,
        ]
    };
    let title = if unavailable {
        " L2 ORDERBOOK NOT AVAILABLE "
    } else {
        " L2 ORDERBOOK LIQUIDITY STACK (BID vs ASK DEPTH) "
    };
    let data = [("Bid Depth", values[0]), ("Ask Depth", values[1])];
    let chart = BarChart::default()
        .block(panel_block(app, title.into(), app.theme.title))
        .data(&data)
        .bar_width(12)
        .bar_gap(4)
        .bar_style(app.theme.bull)
        .value_style(app.theme.gold);
    f.render_widget(chart, area);
}

fn render_distribution_chart(f: &mut Frame, app: &App, area: Rect) {
    let counts = widgets::distribution_counts(app);
    let data = [
        ("TREND_UP", counts[0] as u64),
        ("TREND_DOWN", counts[1] as u64),
        ("BREAKOUT", counts[2] as u64),
        ("TRANSITION", counts[3] as u64),
        ("RANGE", counts[4] as u64),
        ("UNKNOWN", counts[5] as u64),
    ];
    let chart = BarChart::default()
        .block(panel_block(
            app,
            " HISTORICAL REGIME DISTRIBUTION PROFILE ".into(),
            app.theme.title,
        ))
        .data(&data)
        .bar_width(8)
        .bar_gap(2)
        .bar_style(app.theme.cyan)
        .value_style(app.theme.gold);
    f.render_widget(chart, area);
}

fn render_sparklines(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    let prices = app.sparkline_price_data();
    let price = Sparkline::default()
        .block(panel_block(
            app,
            format!(" PRICE TRAJECTORY (${:.2}) ", app.current_snapshot().price),
            app.theme.title,
        ))
        .data(&prices)
        .style(app.theme.cyan);
    f.render_widget(price, chunks[0]);
    if app.backend.is_source_follow() {
        widgets::render_source_readiness_sparkline(f, app, chunks[1]);
    } else {
        render_bbwp_sparkline(f, app, chunks[1]);
    }
}

fn render_bbwp_sparkline(f: &mut Frame, app: &App, area: Rect) {
    let values = app.sparkline_bbwp_data();
    let ready = app.backend.compression_ready == Some(true);
    let threshold = app
        .backend
        .bbwp_compression_threshold
        .map_or_else(|| "N/A".into(), |value| format!("{value:.1}%"));
    let title = format!(
        " BBWP <{threshold} {} ({:.1}%) ",
        if ready { "READY" } else { "WAIT" },
        app.current_snapshot().bbwp_percentile
    );
    let widget = Sparkline::default()
        .block(panel_block(app, title, app.theme.gold))
        .data(&values)
        .style(if ready {
            app.theme.coiling
        } else {
            app.theme.cyan
        });
    f.render_widget(widget, area);
}
