//! Compact cockpit line for provider exits intentionally ignored by live policy.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_ignored_provider_exit::CohortIgnoredProviderExit;
use crate::backend_cohort_trade_reflections::CohortOpenTradeReflection;

pub(crate) fn line<'a>(
    app: &'a App,
    trade: &'a CohortOpenTradeReflection,
    compact: bool,
) -> Line<'a> {
    let Some(observer) = trade.ignored_provider_exit_observer.as_ref() else {
        return Line::from(Span::styled("IGNORED RX TELEMETRY N/A", app.theme.muted));
    };
    let Some(signal) = observer.first_signal.as_ref() else {
        return Line::from(Span::styled(empty_label(observer), app.theme.muted));
    };
    let since = observer
        .path_since_first_signal
        .as_ref()
        .and_then(|path| path.current_directional_return_bps);
    let label = if compact {
        format!(
            "{} | RX{} {} {}",
            entry_relation(trade),
            observer.ignored_signal_count,
            reason_label(&signal.exit_reason, true),
            bps(since),
        )
    } else {
        format!(
            "IGNORED RX {} @{} | ENTRY {:+.1}bps | SINCE {}bps | N{}",
            reason_label(&signal.exit_reason, false),
            full_price(signal.reference_price),
            signal.entry_directional_return_bps,
            bps(since),
            observer.ignored_signal_count,
        )
    };
    Line::from(Span::styled(label, outcome_style(app, since)))
}

fn empty_label(observer: &CohortIgnoredProviderExit) -> &'static str {
    if observer.status == "not_applicable_policy_honors" {
        "RECIPE EXIT HONORED // IGNORED RX N/A"
    } else {
        "IGNORED RX NONE OBSERVED"
    }
}

fn reason_label(reason: &str, compact: bool) -> String {
    let normalized = reason.replace('_', " ").to_uppercase();
    if compact {
        match reason {
            "source_direction_lost" => "LOST".into(),
            "hip3_swing_ha_flip" => "HA FLIP".into(),
            _ => normalized,
        }
    } else {
        normalized
    }
}

fn entry_relation(trade: &CohortOpenTradeReflection) -> String {
    let context = &trade.entry_signal;
    let relation = match context.breakout_side_relation.as_deref() {
        Some("aligned") => "ALIGNED",
        Some("opposed") => "OPPOSED",
        _ => "N/A",
    };
    format!(
        "BK:{} STR:{} {relation}",
        side_code(context.breakout_side.as_deref()),
        side_code(context.structural_direction.as_deref()),
    )
}

fn side_code(side: Option<&str>) -> &'static str {
    match side {
        Some("long") => "L",
        Some("short") => "S",
        _ => "?",
    }
}

fn full_price(price: f64) -> String {
    format!("{price:.2}")
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"))
}

fn outcome_style(app: &App, value: Option<f64>) -> ratatui::style::Style {
    match value {
        Some(number) if number >= 0.0 => app.theme.bull,
        Some(_) => app.theme.bear,
        None => app.theme.muted,
    }
}
