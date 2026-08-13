//! Read-only presentation of effective runtime sizing evidence.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort::CohortProviderSizing;
use crate::backend_cohort_configuration::CohortConfigurationGeneration;
use crate::cohort_format::money;

/// Format portfolio-level cap utilization without implying an execution gate.
pub(crate) fn portfolio_capacity_line<'a>(app: &'a App) -> Line<'a> {
    let Some(evidence) = app.backend.cohort_checkpoint.risk_utilization.as_ref() else {
        return Line::from(Span::styled("SIZE EVIDENCE UNAVAILABLE", app.theme.muted));
    };
    Line::from(vec![
        Span::raw("SIZE CAP "),
        Span::styled(
            format!(
                "{}/{}",
                evidence.cap_bound_assets, evidence.configured_assets
            ),
            if evidence.cap_bound_assets > 0 {
                app.theme.gold
            } else {
                app.theme.bull
            },
        ),
        Span::raw(" // RESERVE "),
        Span::styled(
            format!("{:.2}%", evidence.maximum_effective_margin_fraction * 100.0),
            app.theme.cyan,
        ),
    ])
}

/// Format configured versus effective sizing for one selected asset.
pub(crate) fn asset_sizing_line<'a>(app: &'a App, symbol: &str) -> Line<'a> {
    let evidence = app.backend.cohort_checkpoint.risk_utilization.as_ref();
    let provider = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index);
    let provider_row = evidence.and_then(|risk| {
        let key = format!("{}|{symbol}", provider?.strategy_id);
        risk.by_provider_symbol.get(&key)
    });
    let asset_row = evidence.and_then(|risk| risk.by_asset.get(symbol));
    let Some((row, source)) = provider_row
        .map(|value| (&value.sizing, value.sizing_source.as_str()))
        .or_else(|| asset_row.map(|value| (value, "asset_default")))
    else {
        return Line::from(vec![
            Span::raw(format!("LIVE SIZING {symbol}  ")),
            Span::styled("EVIDENCE UNAVAILABLE // REPORT ONLY", app.theme.muted),
        ]);
    };
    let state = if row.cap_binding {
        "CAP BOUND"
    } else {
        "FRACTIONAL"
    };
    let source = match source {
        "provider_override" => "PROVIDER OVERRIDE",
        _ => "ASSET DEFAULT",
    };
    Line::from(vec![
        Span::raw(format!("LIVE SIZING {symbol}  ")),
        Span::styled(
            format!("{state} / {source}"),
            if row.cap_binding {
                app.theme.gold
            } else {
                app.theme.bull
            },
        ),
        Span::raw(format!(
            " // CONFIG {:.2}% -> EFFECTIVE {:.2}% // REQUEST {} -> PLAN {} // ",
            row.configured_margin_fraction * 100.0,
            row.effective_margin_fraction * 100.0,
            money(row.uncapped_notional_usd),
            money(row.planned_notional_usd),
        )),
        Span::styled("REPORT ONLY", app.theme.cyan),
    ])
}

/// Format the provider sizing currently present in the restart profile on disk.
pub(crate) fn staged_provider_sizing_line<'a>(app: &'a App, symbol: &str) -> Line<'a> {
    let provider = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index);
    let generation = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref();
    let activation = staged_activation(generation);
    let directional = generation.and_then(|evidence| {
        let strategy = &provider?.strategy_id;
        let values = evidence
            .current_provider_directional_sizing_overrides
            .as_ref()?;
        Some((
            values.get(&format!("{strategy}|{symbol}|long"))?,
            values.get(&format!("{strategy}|{symbol}|short"))?,
        ))
    });
    if let Some((long, short)) = directional {
        return directional_staged_line(app, symbol, long, short, activation);
    }
    let row = generation.and_then(|evidence| {
        let key = format!("{}|{symbol}", provider?.strategy_id);
        evidence
            .current_provider_sizing_overrides
            .as_ref()?
            .get(&key)
    });
    let Some(sizing) = row else {
        return Line::from(vec![
            Span::raw(format!("NEXT-RUN SIZING {symbol}  ")),
            Span::styled("NO PROVIDER OVERRIDE REPORTED", app.theme.muted),
        ]);
    };
    Line::from(vec![
        Span::raw(format!("NEXT-RUN SIZING {symbol}  ")),
        Span::styled("PROVIDER OVERRIDE", app.theme.gold),
        Span::raw(format!(
            " // CONFIG {:.2}% // CAP {} // ",
            sizing.margin_fraction * 100.0,
            money(sizing.max_notional_usd),
        )),
        Span::styled(activation, app.theme.cyan),
    ])
}

fn staged_activation(generation: Option<&CohortConfigurationGeneration>) -> &'static str {
    if generation.is_some_and(|value| value.matches_runtime) {
        "CURRENT"
    } else {
        "RESTART REQUIRED"
    }
}

fn directional_staged_line<'a>(
    app: &'a App,
    symbol: &str,
    long: &CohortProviderSizing,
    short: &CohortProviderSizing,
    activation: &'a str,
) -> Line<'a> {
    Line::from(vec![
        Span::raw(format!("NEXT-RUN SIZING {symbol}  ")),
        Span::styled(
            format!(
                "LONG {:.2}%/{} // SHORT {:.2}%/{}",
                long.margin_fraction * 100.0,
                money(long.max_notional_usd),
                short.margin_fraction * 100.0,
                money(short.max_notional_usd),
            ),
            app.theme.gold,
        ),
        Span::raw(" // "),
        Span::styled(activation, app.theme.cyan),
    ])
}
