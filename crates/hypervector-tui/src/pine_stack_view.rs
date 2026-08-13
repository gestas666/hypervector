//! Read-only four-Pine forward-observer screen.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Row, Table},
};

use crate::app::App;
use crate::backend_pine_stack::BackendPineComponent;

/// Render the same zero-capital observer truth on the strategy dashboard.
pub fn render_dashboard(f: &mut Frame, app: &App, area: Rect) {
    render_signal_engine(f, app, area);
}

/// Render all four backend-authored Pine components without execution claims.
pub fn render_signal_engine(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(9),
            Constraint::Length(8),
            Constraint::Length(7),
            Constraint::Length(6),
            Constraint::Min(8),
        ])
        .split(area);
    render_directional_components(f, app, chunks[0]);
    render_sentiment(f, app, chunks[1]);
    render_tp_dimensions(f, app, chunks[2]);
    render_observer_contract(f, app, chunks[3]);
    render_decision_audit(f, app, chunks[4]);
}

fn render_directional_components(f: &mut Frame, app: &App, area: Rect) {
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    let pine = &app.backend.pine_stack;
    let cs_lines = vec![
        state_line(app, "STATE", pine.cs_state),
        Line::from(format!(
            "SELECTED FACTOR {} │ TRAILING STOP {}",
            number(pine.cs_selected_factor),
            money(pine.cs_trailing_stop)
        )),
        Line::from(format!(
            "LONG ONSET {} │ SHORT ONSET {}",
            yes_no(pine.cs_long_onset),
            yes_no(pine.cs_short_onset)
        )),
        Line::from("ATR 10 │ SENSITIVITY 5 │ COMPLETED 30m BAR"),
    ];
    render_panel(f, app, columns[0], " CS ADAPTIVE SUPERTREND ", cs_lines);

    let trend_lines = vec![
        state_line(app, "STATE", pine.trend_state),
        Line::from(format!(
            "EPISODE {} bars │ AMBIGUOUS {}",
            integer(pine.trend_episode_bars),
            yes_no(pine.trend_ambiguous)
        )),
        Line::from(format!(
            "HIGH {} │ LOW {} │ MID {}",
            money(pine.trend_episode_high),
            money(pine.trend_episode_low),
            money(pine.trend_episode_mid)
        )),
        Line::from(format!(
            "DELTA {} │ STRUCTURE LOOKBACK 30",
            percent(pine.trend_delta_pct)
        )),
    ];
    render_panel(f, app, columns[1], " TREND LEVELS ", trend_lines);
}

fn render_sentiment(f: &mut Frame, app: &App, area: Rect) {
    let pine = &app.backend.pine_stack;
    let components = pine
        .sentiment_components
        .chunks(4)
        .map(component_line)
        .collect::<Vec<_>>();
    let mut lines = vec![Line::from(vec![
        Span::raw("COMPOSITE "),
        Span::styled(number(pine.sentiment_score), app.theme.gold),
        Span::raw(" │ SUPPORT "),
        Span::styled(integer(pine.sentiment_support), app.theme.cyan),
        Span::raw("/11 │ DISPLAY EVIDENCE; NO ENTRY AUTHORITY"),
    ])];
    lines.extend(components);
    render_panel(f, app, area, " MARKET SENTIMENT · ANNOTATION ONLY ", lines);
}

fn render_tp_dimensions(f: &mut Frame, app: &App, area: Rect) {
    let pine = &app.backend.pine_stack;
    let support = if pine.tp_insufficient_support == Some(true) {
        "INSUFFICIENT"
    } else {
        "AVAILABLE"
    };
    let lines = vec![
        Line::from(format!(
            "SCORE {} │ RAW {} │ DIRECTIONAL POOL {}",
            number(pine.tp_density_score),
            number(pine.tp_density_raw),
            integer(pine.tp_directional_pool)
        )),
        Line::from(format!(
            "RELATIVE VOLUME {} │ RANGE POSITION {}",
            number(pine.tp_relative_volume),
            number(pine.tp_range_position)
        )),
        Line::from(format!(
            "SUPPORT {support} │ MINIMUM {} │ TIME-OF-DAY AXIS OFF",
            integer(pine.tp_minimum_support)
        )),
        Line::from("ANNOTATION ONLY │ NOT A WIN RATE, TARGET ODDS, OR POSITION-SIZING INPUT"),
    ];
    render_panel(
        f,
        app,
        area,
        " TP DIMENSIONS · DENSITY MATCH · NOT PROBABILITY ",
        lines,
    );
}

fn render_observer_contract(f: &mut Frame, app: &App, area: Rect) {
    let action = label(app.backend.latest_decision_action.as_deref());
    let lines = vec![
        Line::from(vec![
            Span::styled("PSEUDO-HOLDOUT FAILED", app.theme.bear),
            Span::raw(" │ FRESH FORWARD EVIDENCE REQUIRED │ SP500 DEFERRED"),
        ]),
        Line::from(format!(
            "ZERO CAPITAL │ AUTHORITY {} │ LIVE FALSE │ ACTION {action}",
            label(app.backend.execution_authority.as_deref())
        )),
        Line::from(format!(
            "LAST COMPLETED BAR {} │ REASON {}",
            app.backend
                .latest_regime_feed_ts
                .as_deref()
                .unwrap_or("N/A"),
            label(app.backend.latest_regime_reason.as_deref())
        )),
    ];
    render_panel(f, app, area, " FOUR-PINE 30m FORWARD OBSERVER ", lines);
}

fn render_decision_audit(f: &mut Frame, app: &App, area: Rect) {
    let rows = app
        .backend
        .pine_stack
        .recent_decisions
        .iter()
        .rev()
        .map(|event| {
            Row::new(vec![
                event.timestamp.clone(),
                state_name(event.cs_state).to_string(),
                state_name(event.trend_state).to_string(),
                label(Some(&event.action)),
                label(Some(&event.reason)),
            ])
        });
    let table = Table::new(
        rows,
        [
            Constraint::Length(26),
            Constraint::Length(8),
            Constraint::Length(8),
            Constraint::Length(24),
            Constraint::Min(20),
        ],
    )
    .header(Row::new([
        "BAR TIME",
        "CS",
        "TREND",
        "OBSERVER ACTION",
        "REASON",
    ]))
    .block(
        Block::default()
            .title(" COMPLETED-BAR BACKEND AUDIT ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );
    f.render_widget(table, area);
}

fn render_panel(f: &mut Frame, app: &App, area: Rect, title: &str, lines: Vec<Line<'static>>) {
    let block = Block::default()
        .title(title)
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn state_line(app: &App, prefix: &str, value: Option<i64>) -> Line<'static> {
    let state = state_name(value);
    let style = match value {
        Some(1) => app.theme.bull,
        Some(-1) => app.theme.bear,
        _ => app.theme.muted,
    };
    Line::from(vec![
        Span::raw(format!("{prefix} ")),
        Span::styled(state, style),
    ])
}

fn component_line(values: &[BackendPineComponent]) -> Line<'static> {
    Line::from(
        values
            .iter()
            .map(|component| {
                format!(
                    "{} {}",
                    component.name.replace('_', " ").to_uppercase(),
                    number(component.value)
                )
            })
            .collect::<Vec<_>>()
            .join(" │ "),
    )
}

fn state_name(value: Option<i64>) -> &'static str {
    match value {
        Some(1) => "BULL",
        Some(-1) => "BEAR",
        Some(0) => "NEUTRAL",
        _ => "N/A",
    }
}

fn yes_no(value: Option<bool>) -> &'static str {
    match value {
        Some(true) => "YES",
        Some(false) => "NO",
        None => "N/A",
    }
}

fn number(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1}"))
}

fn integer(value: Option<u64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| number.to_string())
}

fn money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.2}"))
}

fn percent(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}%"))
}

fn label(value: Option<&str>) -> String {
    value
        .map(|text| text.replace('_', " ").to_uppercase())
        .unwrap_or_else(|| "NOT REPORTED".into())
}
