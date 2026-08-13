//! Four-coin regime pulse with explicit non-probabilistic movement strength.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
};

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_regime::latest_regime;
use crate::cohort_widgets::{panel, render_empty, selected_page};

/// Render exact backend calls for every enabled coin.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.enabled_symbols.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " RANGE DETECTOR ",
            "BACKEND COIN SET UNAVAILABLE",
        );
        return;
    }
    let block = panel(" RANGE DETECTOR // MOVE STRENGTH ≠ PROBABILITY ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints(vec![Constraint::Ratio(1, 4); 4])
        .split(inner);
    let (visible, _) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        4,
    );
    for (index, symbol) in app.backend.cohort.enabled_symbols[visible]
        .iter()
        .enumerate()
    {
        let evaluation = latest_regime(app, symbol);
        let (label, ratio, style) = evaluation.map_or_else(
            || provider_meter(app, symbol),
            |value| range_meter(app, symbol, Some(value)),
        );
        crate::cohort_thick_meter::render(frame, app, rows[index], label, ratio, style);
    }
}

fn provider_meter(app: &App, symbol: &str) -> (String, Option<f64>, Style) {
    let provider = app
        .backend
        .cohort
        .evaluations
        .iter()
        .filter(|value| value.symbol == symbol)
        .max_by_key(|value| value.decision_time_ms);
    let Some(value) = provider else {
        return (
            format!("{symbol:<12} CANONICAL + PROVIDER N/A"),
            None,
            app.theme.muted,
        );
    };
    let readiness = value.readiness.readiness_fraction;
    (
        format!("{symbol:<12} PROVIDER ONLY READY={:.0}%", readiness * 100.0,),
        Some(readiness),
        app.theme.cyan,
    )
}

fn range_meter(
    app: &App,
    symbol: &str,
    evaluation: Option<&CohortProviderEvaluation>,
) -> (String, Option<f64>, Style) {
    let state = evaluation.and_then(|value| value.primary_regime.as_deref());
    let strength = evaluation.and_then(|value| value.confidence);
    let range_call = match state {
        Some("RANGE") => "RANGE",
        Some(_) => "NON-RANGE",
        None => "UNAVAILABLE",
    };
    let state_label = state.unwrap_or("N/A");
    let strength_label =
        strength.map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0));
    let label = format!("{symbol:<5} {state_label:<12} {range_call:<11} MOVE={strength_label}");
    (label, strength, state_style(state_label, app))
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
