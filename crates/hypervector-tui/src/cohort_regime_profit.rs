//! Open-position profit-protection presentation.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_trade_reflections::CohortOpenTradeReflection;

pub(crate) fn profit_line<'a>(
    app: &'a App,
    trade: &'a CohortOpenTradeReflection,
    compact: bool,
) -> Line<'a> {
    let Some(value) = trade.profit_protection.as_ref() else {
        return Line::from(Span::styled("PROFIT RISK N/A", app.theme.muted));
    };
    let locked = value.protected_profit_fraction.map_or_else(
        || "N/A".into(),
        |fraction| format!("{:.0}%", fraction * 100.0),
    );
    let label = if compact {
        format!(
            "RISK {} NOW{} STOP{} LOCK{}",
            unsigned_money(value.marked_to_stop_giveback_usd),
            signed_money(value.estimated_exit_now_net_usd),
            signed_money(value.estimated_stop_net_usd),
            locked,
        )
    } else {
        format!(
            "PROFIT RISK {} // EXIT NOW {} // STOP {} // LOCK {} // DIST {:.1}bps",
            unsigned_money(value.marked_to_stop_giveback_usd),
            signed_money(value.estimated_exit_now_net_usd),
            signed_money(value.estimated_stop_net_usd),
            locked,
            value.stop_distance_from_mark_bps,
        )
    };
    Line::from(Span::styled(label, status_style(app, &value.status)))
}

fn signed_money(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn unsigned_money(value: f64) -> String {
    if value >= 0.0 {
        format!("${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn status_style(app: &App, status: &str) -> ratatui::style::Style {
    match status {
        "current_profit_locked" => app.theme.bull,
        "partial_profit_locked" => app.theme.gold,
        "open_profit_unprotected" => app.theme.bear,
        _ => app.theme.muted,
    }
}
