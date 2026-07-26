//! Navigable read-only view of effective backend configuration.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::Span,
    widgets::{Block, Borders, Paragraph, Row, Table},
};
use serde_json::Value;

use crate::app::App;
use crate::backend_telemetry::BackendTelemetrySnapshot;

/// One human-readable effective backend setting.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigMenuRow {
    pub category: String,
    pub option: String,
    pub value: String,
    pub source: String,
}

/// Flatten backend identity fields into selectable menu rows.
pub fn backend_config_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let mut rows = runtime_rows(backend);
    rows.extend(strategy_rows(backend));
    rows.extend(execution_rows(backend));
    rows.extend(cost_rows(backend));
    rows
}

/// Render effective settings as menu rows without mutating backend state.
pub fn render_backend_configuration(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(8), Constraint::Length(3)])
        .split(area);
    let menu = backend_config_rows(&app.backend);
    let rows = menu.iter().enumerate().map(|(index, item)| {
        let style = if index == app.config.selected_option_index {
            app.theme.highlight
        } else {
            ratatui::style::Style::default()
        };
        Row::new(vec![
            Span::styled(&item.category, app.theme.gold),
            Span::styled(&item.option, app.theme.title),
            Span::styled(&item.value, app.theme.cyan),
            Span::styled(&item.source, app.theme.muted),
        ])
        .style(style)
    });
    let table = Table::new(rows, menu_constraints())
        .header(config_header(app))
        .block(
            Block::default()
                .title(" EFFECTIVE BACKEND CONFIGURATION MENU ")
                .borders(Borders::ALL)
                .border_style(app.theme.border_active),
        );
    f.render_widget(table, chunks[0]);
    let help =
        Paragraph::new("[↑/↓] Select  │  Read only  │  Reset: hypervelocity-shadow-reset --yes")
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(app.theme.border),
            );
    f.render_widget(help, chunks[1]);
}

fn runtime_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Runtime",
            "Execution mode",
            option(&backend.execution_mode),
            "session_start",
        ),
        row(
            "Runtime",
            "Strategy",
            option(&backend.strategy_name),
            "session_start",
        ),
        row(
            "Model",
            "Metalabel mode",
            option(&backend.metalabel_mode),
            "session_start",
        ),
        row(
            "Lifecycle",
            "Shadow reset",
            "explicit CLI only".into(),
            "hypervelocity-shadow-reset --yes",
        ),
        number_row(
            "Runtime",
            "Lookback",
            &backend.runtime,
            "lookback_days",
            "runtime",
            "d",
            1.0,
        ),
        json_row(
            "Order book",
            "Archive enabled",
            &backend.orderbook_archive,
            "enabled",
            "orderbook_archive",
        ),
        number_row(
            "Order book",
            "Archive depth",
            &backend.orderbook_archive,
            "depth_levels",
            "orderbook_archive",
            " levels",
            1.0,
        ),
    ]
}

fn strategy_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Position",
            "Position mode",
            &backend.position_policy,
            "position_mode",
            "position_policy",
        ),
        json_row(
            "Position",
            "Max per symbol",
            &backend.position_policy,
            "max_positions_per_symbol",
            "position_policy",
        ),
        number_row(
            "Risk",
            "Leverage",
            &backend.strategy_params,
            "leverage",
            "strategy_params",
            "x",
            1.0,
        ),
        number_row(
            "Risk",
            "Margin allocation",
            &backend.risk,
            "margin_fraction",
            "risk",
            "%",
            100.0,
        ),
        number_row(
            "Exit",
            "Take-profit target",
            &backend.exits,
            "target_margin_pct",
            "exits",
            "%",
            1.0,
        ),
        json_row(
            "Exit",
            "Target basis",
            &backend.exits,
            "target_basis",
            "exits",
        ),
        json_row(
            "Exit",
            "Range policy",
            &backend.exits,
            "range_policy",
            "exits",
        ),
    ]
}

fn execution_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Orders",
            "Order type",
            &backend.execution_policy,
            "order_type",
            "execution",
        ),
        json_row(
            "Orders",
            "Time in force",
            &backend.execution_policy,
            "time_in_force",
            "execution",
        ),
        number_row(
            "Orders",
            "Entry TTL",
            &backend.execution_policy,
            "entry_ttl_seconds",
            "execution",
            "s",
            1.0,
        ),
        number_row(
            "Orders",
            "Re-entry cooldown",
            &backend.execution_policy,
            "reentry_cooldown_bars",
            "execution",
            " bars",
            1.0,
        ),
    ]
}

fn cost_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Costs",
            "Maker fee",
            &backend.costs,
            "maker_fee_rate",
            "costs",
            "bps",
            10_000.0,
        ),
        json_row(
            "Costs",
            "Funding source",
            &backend.costs,
            "funding_source",
            "costs",
        ),
    ]
}

fn row(category: &str, option: &str, value: String, source: &str) -> ConfigMenuRow {
    ConfigMenuRow {
        category: category.into(),
        option: option.into(),
        value,
        source: source.into(),
    }
}

fn json_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
) -> ConfigMenuRow {
    row(category, option_name, json_value(object.get(key)), source)
}

fn number_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
    suffix: &str,
    multiplier: f64,
) -> ConfigMenuRow {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .map(|number| format!("{:.1}{suffix}", number * multiplier))
        .unwrap_or_else(|| "not reported".into());
    row(category, option_name, value, source)
}

fn json_value(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Number(number)) => number.to_string(),
        Some(Value::Bool(flag)) => flag.to_string(),
        _ => "not reported".into(),
    }
}

fn option(value: &Option<String>) -> String {
    value.clone().unwrap_or_else(|| "not reported".into())
}

fn menu_constraints() -> [Constraint; 4] {
    [
        Constraint::Length(14),
        Constraint::Length(24),
        Constraint::Length(32),
        Constraint::Min(16),
    ]
}

fn config_header(app: &App) -> Row<'static> {
    Row::new(
        ["Category", "Option", "Effective value", "Backend source"]
            .into_iter()
            .map(|label| Span::styled(label, app.theme.header)),
    )
}
