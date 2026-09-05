//! Backend-authored multi-asset regime and range-detection cockpit.

use std::collections::BTreeMap;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table},
};

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_format::fill_time;
use crate::cohort_widgets::{page_label, panel, selected_page};

const REGIME_PROVIDER: &str = "canonical_regime_telemetry_v1";
const LEGACY_REGIME_PROVIDER: &str = "range_onset_bidirectional_v1";

/// Render a full-screen explanation of backend regime and range evidence.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let lower_height = if area.height >= 40 {
        13
    } else if area.height >= 30 {
        11
    } else if area.height >= 25 {
        9
    } else {
        0
    };
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(7),
            Constraint::Min(12),
            Constraint::Length(lower_height),
        ])
        .split(area);
    render_state_matrix(frame, app, sections[0]);
    render_diagnostics(frame, app, sections[1]);
    if lower_height > 0 {
        render_lower_deck(frame, app, sections[2]);
    }
}

fn render_state_matrix(frame: &mut Frame, app: &App, area: Rect) {
    let header = Row::new([
        "COIN",
        "1M EXEC",
        "5M PRIMARY",
        "15M CONTEXT",
        "CALL",
        "MOVE/READY",
        "BAR",
    ])
    .style(app.theme.header);
    let capacity = usize::from(area.height.saturating_sub(3).max(1));
    let (visible, _) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        capacity,
    );
    let rows = app.backend.cohort.enabled_symbols[visible.clone()]
        .iter()
        .map(|symbol| {
            let evaluation = latest_regime(app, symbol);
            let observed = latest_provider(app, symbol);
            let values = matrix_values(symbol, evaluation, observed);
            Row::new(values.into_iter().enumerate().map(|(index, value)| {
                let style = if (1..=4).contains(&index) {
                    state_style(&value, app)
                } else {
                    app.theme.muted
                };
                Cell::from(value).style(style)
            }))
        });
    let table = Table::new(
        rows,
        [
            Constraint::Length(13),
            Constraint::Length(14),
            Constraint::Length(15),
            Constraint::Length(16),
            Constraint::Length(14),
            Constraint::Length(11),
            Constraint::Min(12),
        ],
    )
    .header(header)
    .column_spacing(1)
    .block(panel(
        format!(
            " REGIME COMMAND DECK // MULTI-TIMEFRAME STATE MATRIX // ASSETS {} ",
            page_label(&visible, app.backend.cohort.enabled_symbols.len())
        ),
        app,
    ));
    frame.render_widget(table, area);
}

fn matrix_values(
    symbol: &str,
    evaluation: Option<&CohortProviderEvaluation>,
    observed: Option<&CohortProviderEvaluation>,
) -> [String; 7] {
    let Some(value) = evaluation else {
        let Some(provider) = observed else {
            return [
                symbol.into(),
                "N/A".into(),
                "N/A".into(),
                "N/A".into(),
                "AWAITING".into(),
                "N/A".into(),
                "N/A".into(),
            ];
        };
        return [
            symbol.into(),
            "NOT CLASS".into(),
            "NOT CLASS".into(),
            "NOT CLASS".into(),
            provider_call(provider),
            format!("R{:.0}%", provider.readiness.readiness_fraction * 100.0),
            fill_time(provider.decision_time_ms),
        ];
    };
    [
        symbol.into(),
        optional_state(value.state_1m.as_deref()),
        optional_state(value.state_5m.as_deref()),
        optional_state(value.context_15m.as_deref()),
        optional_state(value.primary_regime.as_deref()),
        value
            .confidence
            .map_or_else(|| "N/A".into(), |score| format!("{:.1}%", score * 100.0)),
        fill_time(value.decision_time_ms),
    ]
}

fn provider_call(provider: &CohortProviderEvaluation) -> String {
    let action = match provider.decision_action.as_str() {
        "hold" => "HOLD",
        "enter_long" | "enter_short" => "ENTER",
        "close_long" | "close_short" | "close_open_position" => "CLOSE",
        _ => "EVENT",
    };
    format!("PROV {action}")
}

fn render_diagnostics(frame: &mut Frame, app: &App, area: Rect) {
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(34), Constraint::Percentage(66)])
        .split(area);
    let left = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(52), Constraint::Percentage(48)])
        .split(columns[0]);
    crate::cohort_regime_dynamics::render(frame, app, left[0]);
    crate::cohort_regime_signals::render(frame, app, left[1]);
    crate::cohort_regime_focus::render(frame, app, columns[1]);
}

fn render_lower_deck(frame: &mut Frame, app: &App, area: Rect) {
    if area.width >= 150 {
        render_wide_lower_deck(frame, app, area);
    } else {
        render_compact_lower_deck(frame, app, area);
    }
}

fn render_wide_lower_deck(frame: &mut Frame, app: &App, area: Rect) {
    let columns = Layout::horizontal([
        Constraint::Percentage(22),
        Constraint::Percentage(26),
        Constraint::Percentage(28),
        Constraint::Percentage(24),
    ])
    .split(area);
    render_label_tape(frame, app, columns[0]);
    crate::cohort_regime_open::render(frame, app, columns[1]);
    crate::cohort_regime_reflection::render(frame, app, columns[2]);
    crate::cohort_regime_arbitration::render(frame, app, columns[3]);
}

fn render_compact_lower_deck(frame: &mut Frame, app: &App, area: Rect) {
    let columns = Layout::horizontal([
        Constraint::Percentage(27),
        Constraint::Percentage(35),
        Constraint::Percentage(38),
    ])
    .split(area);
    render_label_tape(frame, app, columns[0]);
    crate::cohort_regime_open::render(frame, app, columns[1]);
    crate::cohort_regime_arbitration::render(frame, app, columns[2]);
}

fn render_label_tape(frame: &mut Frame, app: &App, area: Rect) {
    let grouped = grouped_history(app);
    let title = if area.width < 50 {
        " CANONICAL LABEL TAPE "
    } else {
        " CANONICAL LABEL TAPE // OLDEST → NEWEST "
    };
    let block = panel(title, app);
    let inner = block.inner(area);
    let capacity = usize::from(inner.height).max(1);
    let (visible, _) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        capacity,
    );
    let lines = app.backend.cohort.enabled_symbols[visible]
        .iter()
        .map(|symbol| history_line(app, symbol, grouped.get(symbol)))
        .collect::<Vec<_>>();
    frame.render_widget(block, area);
    frame.render_widget(Paragraph::new(lines), inner);
}

fn history_line<'a>(
    app: &'a App,
    symbol: &'a str,
    history: Option<&Vec<&'a CohortProviderEvaluation>>,
) -> Line<'a> {
    let mut spans = vec![Span::styled(format!("{symbol:<12} "), app.theme.cyan)];
    let Some(values) = history else {
        let provider_only = app
            .backend
            .cohort
            .evaluations
            .iter()
            .any(|value| value.symbol == symbol && !is_regime_provider(&value.strategy_id));
        let label = if provider_only {
            "PROV-ONLY REG N/A"
        } else {
            "NO REGIME HISTORY"
        };
        spans.push(Span::styled(label, app.theme.muted));
        return Line::from(spans);
    };
    for value in values.iter().rev().take(32).rev() {
        let state = value.primary_regime.as_deref().unwrap_or("UNKNOWN");
        spans.push(Span::styled(state_glyph(state), state_style(state, app)));
    }
    Line::from(spans)
}

fn grouped_history(app: &App) -> BTreeMap<String, Vec<&CohortProviderEvaluation>> {
    let mut grouped: BTreeMap<String, Vec<&CohortProviderEvaluation>> = BTreeMap::new();
    for value in &app.backend.cohort.regime_history {
        grouped.entry(value.symbol.clone()).or_default().push(value);
    }
    grouped
}

pub(crate) fn latest_regime<'a>(
    app: &'a App,
    symbol: &str,
) -> Option<&'a CohortProviderEvaluation> {
    app.backend
        .cohort
        .regime_history
        .iter()
        .chain(app.backend.cohort.evaluations.iter())
        .filter(|value| is_regime_provider(&value.strategy_id) && value.symbol == symbol)
        .max_by_key(|value| (value.decision_time_ms, value.strategy_id == REGIME_PROVIDER))
}

fn is_regime_provider(strategy_id: &str) -> bool {
    matches!(strategy_id, REGIME_PROVIDER | LEGACY_REGIME_PROVIDER)
}

fn latest_provider<'a>(app: &'a App, symbol: &str) -> Option<&'a CohortProviderEvaluation> {
    app.backend
        .cohort
        .evaluations
        .iter()
        .filter(|value| value.symbol == symbol)
        .max_by_key(|value| value.decision_time_ms)
}

fn optional_state(value: Option<&str>) -> String {
    value.unwrap_or("N/A").to_string()
}

fn state_glyph(state: &str) -> &'static str {
    match state {
        "TREND_UP" => "▲",
        "TREND_DOWN" => "▼",
        "BREAKOUT" => "◆",
        "RANGE" => "■",
        "TRANSITION" => "◇",
        _ => "·",
    }
}

fn state_style(state: &str, app: &App) -> Style {
    match state {
        "TREND_UP" => app.theme.bull,
        "TREND_DOWN" => app.theme.bear,
        "BREAKOUT" => app.theme.cyan,
        "RANGE" => app.theme.coiling,
        "TRANSITION" => app.theme.carry,
        _ => app.theme.muted,
    }
}
