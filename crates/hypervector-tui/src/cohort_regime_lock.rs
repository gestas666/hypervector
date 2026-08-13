//! Compact open profit-lock counterfactual for the regime cockpit.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_open_profit_lock::CohortOpenProfitLockPolicy;
use crate::backend_cohort_trade_reflections::CohortOpenTradeReflection;

const POLICIES: [(&str, &str); 3] = [
    ("a25_floor15_trail10", "25"),
    ("a40_floor15_trail20", "40"),
    ("a60_floor15_trail30", "60"),
];

pub(crate) fn line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let Some(lock) = trade.open_profit_lock_challenger.as_ref() else {
        return Line::from(Span::styled("LOCK OBSERVER N/A", app.theme.muted));
    };
    if lock.status == "insufficient_candle_coverage" {
        return Line::from(Span::styled(
            format!(
                "LOCK WITHHELD {}/{} BARS",
                lock.completed_bars_observed, lock.completed_bars_expected
            ),
            app.theme.bear,
        ));
    }
    if lock.status == "awaiting_completed_bar" {
        return Line::from(Span::styled("LOCK AWAITING COMPLETED BAR", app.theme.muted));
    }
    let mut spans = vec![Span::styled("LOCK ", app.theme.header)];
    for (index, (key, activation)) in POLICIES.iter().enumerate() {
        if index > 0 {
            spans.push(Span::raw(" "));
        }
        spans.push(policy_span(app, activation, lock.policies.get(*key)));
    }
    Line::from(spans)
}

fn policy_span<'a>(
    app: &'a App,
    activation: &str,
    policy: Option<&CohortOpenProfitLockPolicy>,
) -> Span<'a> {
    let Some(value) = policy else {
        return Span::styled(format!("?{activation}"), app.theme.bear);
    };
    match value.status.as_str() {
        "triggered_before_current_boundary" => Span::styled(
            format!(
                "H{activation}@{}{}",
                price(value.trigger_reference_price),
                estimated_net(value)
            ),
            app.theme.gold,
        ),
        "armed_not_triggered" => Span::styled(
            format!(
                "A{activation}@{}{}",
                price(value.active_stop_price),
                estimated_net(value)
            ),
            app.theme.bull,
        ),
        "not_activated" => Span::styled(format!("W{activation}"), app.theme.muted),
        "withheld_incomplete_candle_coverage" => {
            Span::styled(format!("X{activation}"), app.theme.bear)
        }
        _ => Span::styled(format!("?{activation}"), app.theme.bear),
    }
}

fn estimated_net(policy: &CohortOpenProfitLockPolicy) -> String {
    policy
        .counterfactual_economics
        .as_ref()
        .map_or_else(String::new, |value| {
            format!("/{:+.2}", value.estimated_net_pnl_excluding_funding_usd)
        })
}

fn price(value: Option<f64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |number| {
            if number >= 100.0 {
                format!("{number:.2}")
            } else if number >= 1.0 {
                format!("{number:.4}")
            } else {
                format!("{number:.6}")
            }
        },
    )
}
