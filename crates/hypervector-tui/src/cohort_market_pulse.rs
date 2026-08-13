//! Cross-asset market, position, depth, and setup-proximity overview.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_format::number;
use crate::cohort_widgets::{
    page_label, panel, position_style, provider_alias, render_empty, selected_page,
};

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.enabled_symbols.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " MARKET PULSE // SETUP PROXIMITY ",
            "No backend-authored market universe is available",
        );
        return;
    }
    let capacity = usize::from(area.height.saturating_sub(3).max(1));
    let (visible, _) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        capacity,
    );
    let symbols = app
        .backend
        .cohort
        .enabled_symbols
        .get(visible.clone())
        .unwrap_or(&[]);
    let label = page_label(&visible, app.backend.cohort.enabled_symbols.len());
    if area.width < 100 {
        render_compact(frame, app, area, symbols, &label);
        return;
    }
    render_wide(frame, app, area, symbols, &label);
}

fn render_wide(frame: &mut Frame, app: &App, area: Rect, symbols: &[String], label: &str) {
    let rows = symbols.iter().map(|symbol| market_row(app, symbol));
    let table = Table::new(
        rows,
        [
            Constraint::Length(13),
            Constraint::Length(9),
            Constraint::Length(10),
            Constraint::Length(11),
            Constraint::Length(10),
            Constraint::Length(10),
            Constraint::Length(14),
            Constraint::Length(16),
            Constraint::Min(20),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new([
            "COIN",
            "AUTH",
            "POSITION",
            "MARK",
            "L2 SPREAD",
            "L2 OPI",
            "READINESS",
            "LEADING SETUP",
            "NEXT BLOCKER",
        ])
        .style(app.theme.header),
    )
    .block(panel(
        format!(" MARKET PULSE // SETUP PROXIMITY // ASSETS {label} // BACKEND AUTHORED "),
        app,
    ));
    frame.render_widget(table, area);
}

fn render_compact(frame: &mut Frame, app: &App, area: Rect, symbols: &[String], label: &str) {
    let rows = symbols.iter().map(|symbol| compact_market_row(app, symbol));
    let table = Table::new(
        rows,
        [
            Constraint::Length(13),
            Constraint::Length(9),
            Constraint::Length(8),
            Constraint::Length(7),
            Constraint::Length(9),
            Constraint::Length(14),
            Constraint::Min(15),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new([
            "COIN",
            "AUTH",
            "POSITION",
            "L2 OPI",
            "READY",
            "TOP SETUP",
            "NEXT BLOCKER",
        ])
        .style(app.theme.header),
    )
    .block(panel(
        format!(" MARKET PULSE // SETUP PROXIMITY // ASSETS {label} "),
        app,
    ));
    frame.render_widget(table, area);
}

fn market_row<'a>(app: &'a App, symbol: &'a str) -> Row<'a> {
    let asset = app
        .backend
        .cohort
        .assets
        .iter()
        .find(|value| value.symbol == symbol);
    let book = app.backend.cohort.books.get(symbol);
    let setup = leading_setup(app, symbol);
    let position = match asset.and_then(|value| value.position_side.as_deref()) {
        Some(value) => value.to_uppercase(),
        None if app.backend.live_armed == Some(false) => "DISARMED".into(),
        None if asset.is_some() => "FLAT".into(),
        None => "UNREPORTED".into(),
    };
    let mark = asset
        .and_then(|value| value.mark_price)
        .or_else(|| book.map(|value| value.mid_px));
    Row::new(vec![
        Cell::from(symbol).style(app.theme.title),
        Cell::from(authority_label(app, symbol)).style(app.theme.cyan),
        Cell::from(position)
            .style(asset.map_or(app.theme.muted, |value| position_style(value, app))),
        Cell::from(number(mark)),
        Cell::from(book.map_or_else(
            || "N/A".into(),
            |value| format!("{:.3}bps", value.spread_bps),
        )),
        Cell::from(book.map_or_else(|| "N/A".into(), |value| format!("{:+.3}", value.opi))),
        Cell::from(readiness_label(setup)),
        Cell::from(setup.map_or("N/A", |value| provider_alias(&value.strategy_id))),
        Cell::from(blocker_label(setup)),
    ])
}

fn compact_market_row<'a>(app: &'a App, symbol: &'a str) -> Row<'a> {
    let asset = app
        .backend
        .cohort
        .assets
        .iter()
        .find(|value| value.symbol == symbol);
    let book = app.backend.cohort.books.get(symbol);
    let setup = leading_setup(app, symbol);
    let position = asset
        .and_then(|value| value.position_side.as_deref())
        .map_or("FLAT".into(), str::to_uppercase);
    Row::new(vec![
        Cell::from(symbol).style(app.theme.title),
        Cell::from(authority_label(app, symbol)).style(app.theme.cyan),
        Cell::from(position)
            .style(asset.map_or(app.theme.muted, |value| position_style(value, app))),
        Cell::from(book.map_or_else(|| "N/A".into(), |value| format!("{:+.3}", value.opi))),
        Cell::from(readiness_label(setup)),
        Cell::from(setup.map_or("N/A", |value| provider_alias(&value.strategy_id))),
        Cell::from(blocker_label(setup)),
    ])
}

fn authority_label(app: &App, symbol: &str) -> &'static str {
    let executable = app.backend.cohort.providers.iter().any(|provider| {
        provider
            .execution_symbols
            .as_ref()
            .is_some_and(|symbols| symbols.iter().any(|value| value == symbol))
    });
    if executable {
        return if app.backend.live_armed == Some(true) {
            "LIVE"
        } else {
            "CANARY"
        };
    }
    if app
        .backend
        .cohort
        .providers
        .iter()
        .any(|provider| provider.symbols.iter().any(|value| value == symbol))
    {
        "OBSERVE"
    } else {
        "UNSCOPED"
    }
}

fn readiness_label(setup: Option<&CohortProviderEvaluation>) -> String {
    setup.map_or_else(
        || "N/A".into(),
        |value| {
            format!(
                "{}/{} {:>3.0}%",
                value.readiness.conditions_met,
                value.readiness.conditions_required,
                value.readiness.readiness_fraction * 100.0,
            )
        },
    )
}

fn blocker_label(setup: Option<&CohortProviderEvaluation>) -> String {
    let Some(value) = setup else {
        return "NO EVALUATION".into();
    };
    value
        .readiness
        .blockers
        .first()
        .map(|blocker| crate::cohort_router_format::human_token(blocker))
        .unwrap_or_else(|| {
            if value.eligible {
                "ELIGIBLE / ROUTER DECIDES".into()
            } else {
                value.reason.clone()
            }
        })
}

fn leading_setup<'a>(app: &'a App, symbol: &str) -> Option<&'a CohortProviderEvaluation> {
    app.backend
        .cohort
        .evaluations
        .iter()
        .filter(|value| value.symbol == symbol)
        .max_by(|left, right| {
            left.readiness
                .readiness_fraction
                .total_cmp(&right.readiness.readiness_fraction)
                .then(left.decision_time_ms.cmp(&right.decision_time_ms))
        })
}
