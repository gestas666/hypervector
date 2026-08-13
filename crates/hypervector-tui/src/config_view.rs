//! Navigable read-only view of effective backend configuration.

#[path = "config_view_execution_rows.rs"]
mod config_view_execution_rows;
#[path = "config_view_format.rs"]
mod config_view_format;
#[path = "config_view_runtime_rows.rs"]
mod config_view_runtime_rows;
#[path = "config_view_strategy_rows.rs"]
mod config_view_strategy_rows;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::Span,
    widgets::{Block, Borders, Paragraph, Row, Table},
};

use self::config_view_execution_rows::{cost_rows, execution_rows};
use self::config_view_runtime_rows::{
    apex_mm_runtime_rows, observer_rows, runtime_rows, source_follow_evidence_rows,
};
use self::config_view_strategy_rows::strategy_rows;
use crate::app::App;
use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::config_pine_stack::pine_stack_config_rows;
use crate::config_regime::regime_rows;

pub use self::config_view_format::ConfigMenuRow;
pub(crate) use self::config_view_format::{json_row, json_value, number_row, row};

/// Flatten backend identity fields into selectable menu rows.
pub fn backend_config_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    if backend.is_apex_mm() {
        let mut rows = apex_mm_runtime_rows(backend);
        rows.extend(strategy_rows(backend));
        rows.extend(execution_rows(backend));
        rows.extend(cost_rows(backend));
        return rows;
    }
    if backend.is_pine_stack() {
        return pine_stack_config_rows(backend);
    }
    let mut rows = runtime_rows(backend);
    rows.extend(strategy_rows(backend));
    if backend.is_source_follow() {
        rows.extend(source_follow_evidence_rows(backend));
    }
    rows.extend(regime_rows(backend));
    rows.extend(observer_rows(backend));
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
    let selected = app
        .config
        .selected_option_index
        .min(menu.len().saturating_sub(1));
    let visible_rows = chunks[0].height.saturating_sub(3) as usize;
    let (start, end) = config_viewport(selected, menu.len(), visible_rows);
    let rows = menu[start..end].iter().enumerate().map(|(offset, item)| {
        let index = start + offset;
        let style = if index == selected {
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
                .title(format!(
                    " EFFECTIVE BACKEND CONFIGURATION | SELECTED {}/{} | SHOWING {}-{} ",
                    selected + usize::from(!menu.is_empty()),
                    menu.len(),
                    start + usize::from(!menu.is_empty()),
                    end
                ))
                .borders(Borders::ALL)
                .border_style(app.theme.border_active),
        );
    f.render_widget(table, chunks[0]);
    let help_text = selected_config_detail(menu.get(selected));
    let help = Paragraph::new(help_text).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );
    f.render_widget(help, chunks[1]);
}

fn config_viewport(selected: usize, total: usize, capacity: usize) -> (usize, usize) {
    if total == 0 || capacity == 0 {
        return (0, 0);
    }
    let end = (selected + 1).max(capacity).min(total);
    (end.saturating_sub(capacity), end)
}

fn selected_config_detail(selected: Option<&ConfigMenuRow>) -> String {
    selected.map_or_else(
        || "SELECTED none | BACKEND CONFIGURATION NOT REPORTED".into(),
        |row| {
            format!(
                "SELECTED {} / {} = {} | SOURCE {} | READ ONLY",
                row.category, row.option, row.value, row.source
            )
        },
    )
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
