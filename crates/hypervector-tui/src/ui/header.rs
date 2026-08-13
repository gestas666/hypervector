//! Backend status, navigation header, and timeline ribbon rendering.

use ratatui::{
    Frame,
    layout::{Alignment, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph},
};

use crate::{app::App, backend_telemetry::BackendConnectionState, model::RegimeState};

pub(super) fn render_backend_only(f: &mut Frame, app: &App) {
    let state = connection_label(app);
    let account = app.backend.equity_history.last().map_or_else(
        || "equity=not reported trades=not reported position=not reported".to_string(),
        |equity| {
            format!(
                "equity=${equity:.2} trades={} position={}",
                app.paper_stats.total_trades, app.active_position.direction
            )
        },
    );
    let lines = vec![
        Line::from(format!("BACKEND {state}: {}", app.backend.status_message)),
        Line::from(format!(
            "run={} strategy={} mode={}",
            app.backend.run_id.as_deref().unwrap_or("unknown"),
            app.backend.strategy_name.as_deref().unwrap_or("unknown"),
            app.backend.execution_mode.as_deref().unwrap_or("unknown"),
        )),
        Line::from(account),
        Line::from("Market/regime snapshots unavailable; no local fallback was generated."),
    ];
    let block = Block::default()
        .title(" READ-ONLY BACKEND TELEMETRY ")
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(lines).block(block), f.area());
}

pub(super) fn render_header(f: &mut Frame, app: &App, area: Rect) {
    if area.width < 150 {
        render_compact_header(f, app, area);
        return;
    }
    let mut spans = navigation_spans(app);
    spans.extend(timeframe_role_spans(app));
    spans.extend(status_spans(app));
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);
    f.render_widget(
        Paragraph::new(Line::from(spans))
            .block(block)
            .alignment(Alignment::Left),
        area,
    );
}

fn navigation_spans(app: &App) -> Vec<Span<'static>> {
    let active = |tab| tab_style(app, tab);
    let regime = if app.backend.is_apex_mm() {
        " [2] MICROSTRUCTURE "
    } else if app.backend.is_pine_stack() {
        " [2] PINE SIGNALS "
    } else if app.backend.is_hulk_smash() {
        " [2] SIGNAL ENGINE "
    } else {
        " [2] REGIME DETECTION "
    };
    vec![
        Span::styled(" HYPERVECTOR ENGINE ", app.theme.title),
        Span::raw("│ "),
        Span::styled(" [1] DASHBOARD ", active(0)),
        Span::raw("│ "),
        Span::styled(regime, active(1)),
        Span::raw("│ "),
        Span::styled(" [3] CHART ", active(2)),
        Span::raw("│ "),
        Span::styled(" [4] CONFIG ", active(3)),
        Span::raw("│ "),
        Span::styled(format!("SYMBOL: {}", app.symbol), app.theme.gold),
        Span::raw(" │ "),
    ]
}

fn status_spans(app: &App) -> Vec<Span<'static>> {
    let spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    let spinner = spinner_frames[(app.tick_count % spinner_frames.len() as u64) as usize];
    let (mode, style) = if app.is_live {
        (
            format!("{spinner} REAL-TIME LIVE ORDERBOOK STREAM"),
            app.theme.bull,
        )
    } else {
        ("▶️ REAL HISTORICAL MARKET DATA".into(), app.theme.cyan)
    };
    let status = if app.is_playing { "PLAYING" } else { "PAUSED" };
    vec![
        Span::raw(" │ "),
        Span::styled(mode, style),
        Span::raw(" │ "),
        Span::styled(
            format!("[{status}] ({:.1}x)", app.playback_speed),
            app.theme.header,
        ),
    ]
}

fn render_compact_header(f: &mut Frame, app: &App, area: Rect) {
    let execution = match app.backend.execution_mode.as_deref() {
        Some("live") if app.backend.live_armed == Some(true) => "LIVE ARMED",
        Some("live") => "LIVE DISARMED",
        Some("shadow") => "SHADOW",
        Some("paper") => "PAPER",
        Some(_) => "DISARMED",
        None => "UNREPORTED",
    };
    let line = Line::from(vec![
        Span::styled(" HV ", app.theme.title),
        Span::raw("|"),
        Span::styled(" [1] DASH ", tab_style(app, 0)),
        Span::styled("[2] REGIME ", tab_style(app, 1)),
        Span::styled("[3] CHART ", tab_style(app, 2)),
        Span::styled("[4] CONFIG ", tab_style(app, 3)),
        Span::styled(format!("| {} | ", app.symbol), app.theme.gold),
        Span::styled(compact_timeframe_role(app), app.theme.cyan),
        Span::styled(format!(" | EXEC {execution}"), app.theme.gold),
        Span::styled(
            format!(" | FEED {}", if app.is_live { "LIVE" } else { "PLAYBACK" }),
            app.theme.cyan,
        ),
        Span::styled(format!(" | {}", connection_label(app)), app.theme.title),
    ]);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(line).block(block), area);
}

fn tab_style(app: &App, tab: usize) -> Style {
    if app.active_tab == tab {
        app.theme.highlight
    } else {
        app.theme.muted
    }
}

fn connection_label(app: &App) -> &'static str {
    match app.backend.connection {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    }
}

fn compact_timeframe_role(app: &App) -> String {
    let policy = &app.backend.regime_policy;
    if app.backend.is_source_follow() {
        let decision = policy
            .get("primary_timeframe")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("N/A");
        let pulse = policy
            .get("entry_pulse_seconds")
            .and_then(serde_json::Value::as_f64)
            .map_or_else(|| "N/A".into(), |value| format!("{value:.0}s"));
        return format!("{decision}/{pulse}");
    }
    policy
        .get("execution_timeframe")
        .or_else(|| policy.get("signal_timeframe"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or(&app.timeframe)
        .to_string()
}

fn timeframe_role_spans(app: &App) -> Vec<Span<'static>> {
    if app.backend.is_apex_mm() {
        return apex_timeframe_spans(app);
    }
    if app.backend.is_pine_stack() {
        return single_signal_spans(app, "AUTHORITY: OBSERVE ONLY");
    }
    if app.backend.is_hulk_smash() {
        return hulk_timeframe_spans(app);
    }
    if app.backend.is_source_follow() {
        return source_follow_timeframe_spans(app);
    }
    canonical_timeframe_spans(app)
}

fn apex_timeframe_spans(app: &App) -> Vec<Span<'static>> {
    let refresh = policy_number(app, "quote_refresh_ms", "unreported", "ms");
    let depth = policy_number(app, "depth_levels", "unreported", "");
    vec![
        Span::styled(format!("QUOTE: {refresh}"), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(format!("BOOK: L2/{depth}"), app.theme.title),
    ]
}

fn policy_number(app: &App, key: &str, missing: &str, suffix: &str) -> String {
    app.backend
        .execution_policy
        .get(key)
        .and_then(serde_json::Value::as_f64)
        .map_or_else(|| missing.into(), |value| format!("{value:.0}{suffix}"))
}

fn single_signal_spans(app: &App, authority: &'static str) -> Vec<Span<'static>> {
    let signal = app
        .backend
        .regime_policy
        .get("signal_timeframe")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("not reported")
        .to_string();
    vec![
        Span::styled(format!("SIGNAL: {signal}"), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(authority, app.theme.gold),
    ]
}

fn hulk_timeframe_spans(app: &App) -> Vec<Span<'static>> {
    let policy = &app.backend.regime_policy;
    let signal = policy
        .get("signal_timeframe")
        .and_then(serde_json::Value::as_str);
    let execution = policy
        .get("execution_timeframe")
        .and_then(serde_json::Value::as_str);
    vec![
        Span::styled(
            format!("SIGNAL: {}", signal.unwrap_or("not reported")),
            app.theme.cyan,
        ),
        Span::raw(" │ "),
        Span::styled(
            format!("EXEC: {}", execution.unwrap_or("not reported")),
            app.theme.title,
        ),
    ]
}

fn source_follow_timeframe_spans(app: &App) -> Vec<Span<'static>> {
    let policy = &app.backend.regime_policy;
    let decision = policy
        .get("primary_timeframe")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("not reported");
    let pulse = policy
        .get("entry_pulse_seconds")
        .and_then(serde_json::Value::as_f64)
        .map_or_else(|| "not reported".into(), |value| format!("{value:.0}s"));
    vec![
        Span::styled(format!("DECISION: {decision}"), app.theme.cyan),
        Span::raw(" │ "),
        Span::styled(format!("ENTRY WINDOW: {pulse}"), app.theme.title),
    ]
}

fn canonical_timeframe_spans(app: &App) -> Vec<Span<'static>> {
    let policy = &app.backend.regime_policy;
    let execution = policy
        .get("execution_timeframe")
        .and_then(serde_json::Value::as_str);
    let primary = policy
        .get("primary_timeframe")
        .and_then(serde_json::Value::as_str);
    match (execution, primary) {
        (Some(feed), Some(signal)) if feed != signal => vec![
            Span::styled(format!("EXEC: {feed}"), app.theme.cyan),
            Span::raw(" │ "),
            Span::styled(format!("SIGNAL: {signal}"), app.theme.title),
        ],
        (Some(feed), _) => vec![Span::styled(format!("TF: {feed}"), app.theme.cyan)],
        _ => vec![Span::styled(
            format!("TF: {}", app.timeframe),
            app.theme.cyan,
        )],
    }
}

pub(super) fn render_timeline_ribbon(f: &mut Frame, app: &App, area: Rect) {
    if area.width < 5 || app.snapshots.is_empty() {
        return;
    }
    let inner_width = area.width.saturating_sub(2) as usize;
    let start = app.current_index.saturating_sub(inner_width / 2);
    let end = (start + inner_width).min(app.snapshots.len());
    let spans = timeline_spans(app, start, end);
    let block = Block::default()
        .title(timeline_title(app))
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(Line::from(spans)).block(block), area);
}

fn timeline_spans(app: &App, start: usize, end: usize) -> Vec<Span<'static>> {
    app.snapshots[start..end]
        .iter()
        .enumerate()
        .map(|(offset, snap)| {
            let style = match snap.state {
                RegimeState::BullMomentum => app.theme.bull,
                RegimeState::BearMomentum => app.theme.bear,
                RegimeState::VolatilityCoiling => app.theme.coiling,
                RegimeState::FundingCarry => app.theme.carry,
                RegimeState::RangeChop | RegimeState::Unknown => app.theme.chop,
            };
            if start + offset == app.current_index {
                Span::styled("█", style.add_modifier(Modifier::REVERSED))
            } else {
                Span::styled("█", style)
            }
        })
        .collect()
}

fn timeline_title(app: &App) -> String {
    let snap = app.current_snapshot();
    if app.backend.is_apex_mm() {
        return " MM BOOK TIMELINE | REGIME NOT CLASSIFIED | DISPLAY-ONLY MIDPOINTS ".into();
    }
    if app.backend.is_pine_stack() {
        return " PINE FEATURE TIMELINE | 30m COMPLETED BARS | REGIME NOT CLASSIFIED ".into();
    }
    if app.backend.is_source_follow() {
        return format!(
            " SOURCE REGIME TIMELINE | 5m ENTRY AUTHORITY [{}] | 1m/15m NOT CLASSIFIED ",
            snap.trend_5m
        );
    }
    if app.backend.is_hulk_smash() {
        let score = app
            .backend
            .hulk_smash
            .score
            .map_or_else(|| "N/A".into(), |value| value.to_string());
        return format!(
            " HULK SIGNAL TIMELINE | 30m COMPLETED BARS | SCORE {score} | REGIME NOT CLASSIFIED "
        );
    }
    format!(
        " REGIME TIMELINE (Playhead: Inverted) | Active: [{}] | 5m PRIMARY [{}] | 15m CONTEXT [{}] ",
        snap.state.primary_label(),
        snap.trend_5m,
        snap.trend_15m
    )
}
