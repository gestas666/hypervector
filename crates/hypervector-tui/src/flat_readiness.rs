//! Read-only flat-position readiness and measured market-pulse presentation.

use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::ui::format_time_display;

const DISPLAY_FRESHNESS_MS: f64 = 30_000.0;
const WIDE_PANEL_MIN_WIDTH: u16 = 70;
const WIDE_LEFT_COLUMN: usize = 38;

/// Render backend-authored readiness while no position is open.
pub fn render_flat_readiness(f: &mut Frame, app: &App, area: Rect) {
    let fresh = telemetry_is_fresh(app);
    let status_style = if fresh {
        scanning_style(app.tick_count)
    } else {
        app.theme.coiling
    };
    let lines = if area.width >= WIDE_PANEL_MIN_WIDTH {
        wide_lines(app, status_style, fresh)
    } else {
        compact_lines(app, status_style, fresh)
    };
    let block = Block::default()
        .title(" ACTIVE POSITION | ENTRY READINESS ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(status_style);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn wide_lines(app: &App, status_style: Style, fresh: bool) -> Vec<Line<'static>> {
    let snap = app.current_snapshot();
    vec![
        Line::from(format!(
            "SIZE  0.00000 BTC  |  MARK  ${:.2}  |  FLAT",
            snap.price
        )),
        heading_line(app),
        columns("DIRECTION", &direction(app), "SPREAD", &spread(app)),
        columns("REGIME", &regime(app), "BOOK BIAS", &book_bias(app)),
        columns("MAKER", &maker(app), "L2 AGE", &book_age(app)),
        columns("RETRY", &retry(app), "FUNDING", &funding(app)),
        columns(
            "COOLDOWN",
            &cooldown(app),
            "STRUCTURE",
            &structure_score(app),
        ),
        Line::from(recent_decision(app)),
        Line::from(Span::styled(status_label(fresh), status_style)),
    ]
}

fn compact_lines(app: &App, status_style: Style, fresh: bool) -> Vec<Line<'static>> {
    let snap = app.current_snapshot();
    vec![
        Line::from(format!("FLAT | MARK ${:.2}", snap.price)),
        Line::from(format!("DIRECTION {}", direction(app))),
        Line::from(format!("REGIME {}", regime(app))),
        Line::from(format!("MAKER {}", maker(app))),
        Line::from(format!("RETRY {} | COOLDOWN {}", retry(app), cooldown(app))),
        Line::from(format!("SPREAD {} | BIAS {}", spread(app), book_bias(app))),
        Line::from(format!("L2 {} | FUNDING {}", book_age(app), funding(app))),
        Line::from(recent_decision(app)),
        Line::from(Span::styled(status_label(fresh), status_style)),
    ]
}

fn heading_line(app: &App) -> Line<'static> {
    Line::from(vec![
        Span::styled(
            format!("{:<width$}", "ENTRY READINESS", width = WIDE_LEFT_COLUMN),
            app.theme.cyan,
        ),
        Span::styled("MARKET PULSE", app.theme.cyan),
    ])
}

fn columns(left_key: &str, left: &str, right_key: &str, right: &str) -> Line<'static> {
    let left_text = format!("{left_key} {left}");
    Line::from(format!(
        "{left_text:<width$}{right_key} {right}",
        width = WIDE_LEFT_COLUMN
    ))
}

fn direction(app: &App) -> String {
    match (
        app.backend.entry_allowed,
        app.backend.entry_direction.as_deref(),
    ) {
        (Some(true), Some(value)) => value.to_uppercase(),
        (Some(false), _) => "NONE".to_string(),
        _ => "N/A".to_string(),
    }
}

fn regime(app: &App) -> String {
    app.backend
        .latest_regime
        .clone()
        .unwrap_or_else(|| "N/A".to_string())
}

fn maker(app: &App) -> String {
    app.backend
        .pending_entry_direction
        .as_deref()
        .map(|value| format!("PENDING {}", value.to_uppercase()))
        .unwrap_or_else(|| "STANDBY".to_string())
}

fn retry(app: &App) -> String {
    app.backend
        .entry_retry_state
        .as_deref()
        .map(|value| value.replace('_', " ").to_uppercase())
        .unwrap_or_else(|| "N/A".to_string())
}

fn cooldown(app: &App) -> String {
    match app.backend.entry_cooldown_active {
        Some(true) => "ACTIVE".to_string(),
        Some(false) => "CLEAR".to_string(),
        None => "N/A".to_string(),
    }
}

fn spread(app: &App) -> String {
    app.backend
        .book
        .as_ref()
        .map(|book| format!("{:.1} bps", book.spread_bps))
        .unwrap_or_else(|| "N/A".to_string())
}

fn book_bias(app: &App) -> String {
    app.backend
        .book
        .as_ref()
        .map(|book| format!("{:+.1}%", book.opi * 100.0))
        .unwrap_or_else(|| "N/A".to_string())
}

fn book_age(app: &App) -> String {
    if app.backend.book.is_none() {
        return "N/A".to_string();
    }
    if app.book_state.age_ms < 1_000.0 {
        format!("{:.0} ms", app.book_state.age_ms)
    } else {
        format!("{:.1} s", app.book_state.age_ms / 1_000.0)
    }
}

fn funding(app: &App) -> String {
    app.backend
        .funding_rate_hourly
        .map(|rate| format!("{:+.5}%/hr", rate * 100.0))
        .unwrap_or_else(|| "N/A".to_string())
}

fn structure_score(app: &App) -> String {
    app.backend
        .latest_regime_strength_score
        .map(|value| format!("{:.1}%", value * 100.0))
        .unwrap_or_else(|| "N/A".to_string())
}

fn recent_decision(app: &App) -> String {
    let time = app
        .backend
        .latest_regime_feed_ts
        .as_deref()
        .map(format_time_display)
        .unwrap_or_else(|| "N/A".to_string());
    let regime = regime(app);
    let reason = app
        .backend
        .latest_regime_reason
        .as_deref()
        .unwrap_or("not_reported");
    format!("RECENT DECISION {time} | {regime} | {reason}")
}

fn telemetry_is_fresh(app: &App) -> bool {
    app.backend.connection == BackendConnectionState::Connected
        && app.backend.book.is_some()
        && app.book_state.age_ms <= DISPLAY_FRESHNESS_MS
}

fn status_label(fresh: bool) -> &'static str {
    if fresh {
        "<> SCANNING LIVE <>"
    } else {
        "-- TELEMETRY STALE --"
    }
}

fn scanning_style(tick: u64) -> Style {
    let pulse = crate::animation::pulse(tick, 24);
    let brightness = 0.55 + pulse * 0.45;
    Style::default()
        .fg(Color::Rgb(
            0,
            (240.0 * brightness) as u8,
            (255.0 * brightness) as u8,
        ))
        .add_modifier(Modifier::BOLD)
}
