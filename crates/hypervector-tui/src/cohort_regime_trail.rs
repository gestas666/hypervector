//! Compact operator line for backend-authored open post-soft trail evidence.

use ratatui::text::{Line, Span};

use crate::{app::App, backend_cohort_trade_reflections::CohortOpenTradeReflection};

pub(crate) fn line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let Some(evidence) = trade.post_soft_trail_challenger.as_ref() else {
        return Line::from(Span::styled("TRAILS N/A", app.theme.muted));
    };
    let label = [20_u16, 30, 40]
        .map(|giveback| {
            let status = evidence
                .policies
                .get(&giveback)
                .map_or("N/A", |policy| status_label(&policy.status));
            format!("T{giveback} {status}")
        })
        .join(" ");
    let style = if evidence
        .policies
        .values()
        .any(|policy| policy.status == "triggered")
    {
        app.theme.bear
    } else if evidence.status == "observed" {
        app.theme.gold
    } else {
        app.theme.muted
    };
    Line::from(Span::styled(label, style))
}

fn status_label(status: &str) -> &'static str {
    match status {
        "triggered" => "HIT",
        "armed_not_triggered" => "ARMED",
        "pending_soft_deadline" | "awaiting_completed_bar" => "WAIT",
        _ => "N/A",
    }
}
