//! Reusable regime banners, diagnostics, and distribution widgets.

use ratatui::{
    Frame,
    layout::{Alignment, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Sparkline},
};

use super::time::format_timestamp_display;
use crate::{
    app::App,
    model::{RegimeSnapshot, RegimeState, SourceRegimeDiagnostics},
};

pub(super) fn state_style(app: &App, state: RegimeState) -> Style {
    match state {
        RegimeState::BullMomentum => app.theme.bull,
        RegimeState::BearMomentum => app.theme.bear,
        RegimeState::VolatilityCoiling => app.theme.coiling,
        RegimeState::FundingCarry => app.theme.carry,
        RegimeState::RangeChop | RegimeState::Unknown => app.theme.chop,
    }
}

pub(super) fn render_source_readiness_sparkline(f: &mut Frame, app: &App, area: Rect) {
    let confidences = app
        .snapshots
        .iter()
        .map(|snapshot| (snapshot.confidence * 100.0).clamp(0.0, 100.0) as u64)
        .collect::<Vec<_>>();
    let confidence = app
        .backend
        .latest_regime_confidence
        .map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0));
    let signal_range = app
        .backend
        .source_follow_signal_range_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:.1}bps"));
    let (readiness, readiness_style) = source_readiness(app);
    let widget = Sparkline::default()
        .block(
            Block::default()
                .title(format!(" SOURCE READINESS {readiness} "))
                .title_bottom(format!(" CONF {confidence} | RANGE {signal_range} "))
                .title_style(app.theme.gold)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&confidences)
        .style(readiness_style);
    f.render_widget(widget, area);
}

fn source_readiness(app: &App) -> (&'static str, Style) {
    let signal_observed = matches!(
        app.backend.latest_decision_action.as_deref(),
        Some("enter_long" | "enter_short" | "submit_entry")
    );
    match app.backend.entry_allowed {
        Some(true) => ("ENTRY PENDING", app.theme.bull),
        Some(false) if signal_observed => ("SIGNAL OBSERVED", app.theme.gold),
        Some(false) => ("STANDBY", app.theme.cyan),
        None => ("NOT REPORTED", app.theme.coiling),
    }
}

pub(super) fn compact_regime_score_source(source: Option<&str>) -> &str {
    match source {
        Some("mean_multitimeframe_ema_gap_strength_percentile_rank") => "MTF EMA-GAP PCTL RANK",
        Some(value) => value,
        None => "NOT REPORTED",
    }
}

pub(super) fn source_follow_regime_banner(
    app: &App,
    snap: &RegimeSnapshot,
    state_label: &str,
    confidence_pct: f64,
    ticker: &str,
    ticker_style: Style,
) -> Vec<Line<'static>> {
    if let Some(diagnostics) = snap.source_diagnostics.as_ref() {
        return source_follow_diagnostic_banner(
            app,
            snap,
            diagnostics,
            state_label,
            confidence_pct,
            ticker,
            ticker_style,
        );
    }
    source_follow_fallback_banner(app, snap, state_label, confidence_pct, ticker, ticker_style)
}

fn source_follow_fallback_banner(
    app: &App,
    snap: &RegimeSnapshot,
    state_label: &str,
    confidence_pct: f64,
    ticker: &str,
    ticker_style: Style,
) -> Vec<Line<'static>> {
    let gate = backend_f64(&app.backend.regime_policy, "minimum_confidence").unwrap_or(0.0);
    vec![
        Line::from(Span::styled(state_label.to_string(), app.theme.bear)),
        Line::from(vec![
            Span::raw("5m Source Authority: "),
            Span::styled(format!("[{}]", snap.trend_5m), app.theme.gold),
        ]),
        Line::from(format!(
            "Source Confidence: {confidence_pct:.1}% │ Gate >= {:.1}%",
            gate * 100.0
        )),
        Line::from("1m/15m: NOT CLASSIFIED (not entry inputs)"),
        mark_price_line(app, snap, ticker, ticker_style),
        Line::from(format!(
            "Decision: {} │ Completed 5m bars only",
            format_timestamp_display(&snap.timestamp_str)
        )),
    ]
}

fn source_follow_diagnostic_banner(
    app: &App,
    snap: &RegimeSnapshot,
    diagnostics: &SourceRegimeDiagnostics,
    state_label: &str,
    confidence_pct: f64,
    ticker: &str,
    ticker_style: Style,
) -> Vec<Line<'static>> {
    let filtered = if diagnostics.state_filtered {
        "HYSTERESIS FILTERED"
    } else {
        "HYSTERESIS MATCH"
    };
    let adx = diagnostics
        .adx_percentile_rank
        .map(|value| format!("{:.1}%", value * 100.0))
        .unwrap_or_else(|| "N/A".into());
    vec![
        Line::from(format!(
            "5m CONFIRMED [{state_label}] | RAW [{}]",
            diagnostics.raw_primary
        )),
        Line::from(format!(
            "{filtered} | CONF {confidence_pct:.1}% / RAW {:.1}%",
            diagnostics.raw_confidence * 100.0
        )),
        Line::from(format!(
            "ADX PCTL {adx} | RANGE <{:.1}%",
            diagnostics.adx_range_percentile_threshold * 100.0
        )),
        Line::from(format!(
            "EMA {} | BREAK UP {} DOWN {}",
            diagnostics.ema_alignment,
            yes_no(diagnostics.range_break_up),
            yes_no(diagnostics.range_break_down)
        )),
        mark_price_line(app, snap, ticker, ticker_style),
        Line::from(format!(
            "Decision: {} | Completed 5m bars only",
            format_timestamp_display(&snap.timestamp_str)
        )),
    ]
}

fn mark_price_line(
    app: &App,
    snap: &RegimeSnapshot,
    ticker: &str,
    ticker_style: Style,
) -> Line<'static> {
    Line::from(vec![
        Span::raw("Mark Price: "),
        Span::styled(format!("${:.2}", snap.price), app.theme.gold),
        Span::raw(" "),
        Span::styled(ticker.to_string(), ticker_style),
    ])
}

fn yes_no(value: bool) -> &'static str {
    if value { "YES" } else { "NO" }
}

pub(super) fn source_follow_timeframe_matrix(
    app: &App,
    snap: &RegimeSnapshot,
    area: Rect,
) -> Vec<Line<'static>> {
    let bidirectional = app.backend.source_follow_is_bidirectional();
    if area.height < 7 || area.width < 40 {
        return vec![
            Line::from("5m SOURCE ENTRY AUTHORITY"),
            Line::from(if bidirectional {
                "BIDIRECTIONAL EXECUTION"
            } else {
                "SHORT EXECUTION"
            }),
            Line::from("1m/15m NOT CLASSIFIED"),
        ];
    }
    let authority = if bidirectional {
        "BIDIRECTIONAL EXECUTION | COUNTERTREND LONGS OBSERVE ONLY"
    } else {
        "SHORT EXECUTION | SOURCE LONGS OBSERVE ONLY"
    };
    vec![
        Line::from(format!("1m [{}] UNUSED", snap.trend_1m)),
        Line::from(vec![
            Span::styled("5m SOURCE ENTRY AUTHORITY ", app.theme.gold),
            Span::styled(format!("[{}]", snap.trend_5m), app.theme.title),
        ]),
        Line::from(format!("15m [{}] UNUSED", snap.trend_15m)),
        Line::from(Span::styled(
            "Alignment: SINGLE-TIMEFRAME SOURCE SIGNAL",
            app.theme.title,
        )),
        Line::from(Span::styled(authority, app.theme.bull)),
    ]
}

pub(super) fn microstructure_lines(app: &App, snap: &RegimeSnapshot) -> Vec<Line<'static>> {
    let funding = app
        .backend
        .funding_rate_hourly
        .map(|rate| format!("{:+.6}% / hour", rate * 100.0))
        .unwrap_or_else(|| "not reported".into());
    if snap.microstructure_source == "not_available" {
        return vec![
            Line::from("Orderbook telemetry: not available"),
            funding_line(app, funding),
            Line::from("OPI / spread / depth: not reported"),
        ];
    }
    vec![
        Line::from(format!("Source: {}", snap.microstructure_source)),
        Line::from(format!(
            "OPI {:+.2} | Spread {:.1} bps",
            snap.opi, snap.spread_bps
        )),
        Line::from(format!("Bid/ask depth ratio {:.2}x", snap.bid_depth_ratio)),
        funding_line(app, funding),
    ]
}

fn funding_line(app: &App, funding: String) -> Line<'static> {
    Line::from(vec![
        Span::raw("Funding Rate: "),
        Span::styled(funding, app.theme.carry),
    ])
}

pub(super) fn render_distribution_bar(f: &mut Frame, app: &App, area: Rect) {
    if area.width < 10 || app.snapshots.is_empty() {
        return;
    }
    let counts = distribution_counts(app);
    let total = f64::max(counts.iter().sum(), 1.0);
    let pct = counts.map(|count| count / total * 100.0);
    let line = Line::from(vec![
        Span::styled(
            format!("TRANSITION DISTRIBUTION: TREND_UP {:.0}% ", pct[0]),
            app.theme.bull,
        ),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("TREND_DOWN {:.0}% ", pct[1]), app.theme.bear),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("BREAKOUT {:.0}% ", pct[2]), app.theme.coiling),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("TRANSITION {:.0}% ", pct[3]), app.theme.carry),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("RANGE {:.0}% ", pct[4]), app.theme.chop),
        Span::styled("│ ", app.theme.border),
        Span::styled(format!("UNKNOWN {:.0}%", pct[5]), app.theme.muted),
    ]);
    f.render_widget(Paragraph::new(line).alignment(Alignment::Center), area);
}

pub(super) fn distribution_counts(app: &App) -> [f64; 6] {
    if !app.backend.regime_history.is_empty() {
        let mut counts = [0.0; 6];
        for regime in &app.backend.regime_history {
            let index = match regime.as_str() {
                "TREND_UP" => 0,
                "TREND_DOWN" => 1,
                "BREAKOUT" => 2,
                "TRANSITION" => 3,
                "RANGE" => 4,
                _ => 5,
            };
            counts[index] += 1.0;
        }
        return counts;
    }
    let current_ts = &app.current_snapshot().timestamp_str;
    let states = app
        .events
        .iter()
        .filter(|event| &event.timestamp_str <= current_ts)
        .map(|event| event.to_state)
        .collect::<Vec<_>>();
    counts_for_states(if states.is_empty() {
        std::slice::from_ref(&app.current_snapshot().state)
    } else {
        &states
    })
}

fn counts_for_states(states: &[RegimeState]) -> [f64; 6] {
    let mut counts = [0.0; 6];
    for state in states {
        let index = match state {
            RegimeState::BullMomentum => 0,
            RegimeState::BearMomentum => 1,
            RegimeState::VolatilityCoiling => 2,
            RegimeState::FundingCarry => 3,
            RegimeState::RangeChop => 4,
            RegimeState::Unknown => 5,
        };
        counts[index] += 1.0;
    }
    counts
}

fn backend_f64(value: &serde_json::Value, key: &str) -> Option<f64> {
    value.get(key).and_then(serde_json::Value::as_f64)
}
