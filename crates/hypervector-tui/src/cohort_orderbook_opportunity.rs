//! Compact research-inspector lines for causal order-book opportunity context.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_orderbook_opportunity::{
    CohortOrderbookGroup, CohortProviderOrderbookOpportunity,
};
use crate::cohort_eligible_markouts::markout_lines;
use crate::cohort_router_format::human_token;

pub(crate) fn orderbook_lines<'a>(
    evidence: Option<&CohortProviderOrderbookOpportunity>,
    app: &App,
) -> Vec<Line<'a>> {
    let Some(value) = evidence else {
        return Vec::new();
    };
    let mut lines = Vec::new();
    if let Some(clock) = &value.pressure_clock {
        lines.extend([
            Line::from(""),
            Line::from(Span::styled(
                "PROVIDER PRESSURE CLOCK // REPORT ONLY",
                app.theme.cyan,
            )),
            Line::from(format!(
                "UNAVAILABLE {} // CAUSAL BOOK {} // ABSENT/STALE {}",
                clock.pressure_unavailable_evaluations,
                clock.causal_book_available,
                clock.book_absent_or_stale,
            )),
            Line::from(Span::styled(
                "BOOK PRESENT != SIGNAL CONFIRMED",
                app.theme.muted,
            )),
        ]);
    }
    if let Some(context) = &value.eligible_signal_context {
        lines.extend([
            Line::from(""),
            Line::from(Span::styled(
                "ELIGIBLE SIGNAL CONTEXT // REPORT ONLY",
                app.theme.cyan,
            )),
            Line::from(format!(
                "SIGNALS {} // PRESSURE {}",
                context.eligible_signals,
                stance_summary(&context.pressure_stance),
            )),
            Line::from(format!(
                "5M {} // 15M {}",
                stance_summary(&context.state_5m_stance),
                stance_summary(&context.context_15m_stance),
            )),
        ]);
        lines.extend(markout_lines(context.executable_bbo_markouts.as_ref(), app));
        lines.push(Line::from(Span::styled(
            "SIGNALS != ROUTES OR FILLS",
            app.theme.muted,
        )));
    }
    if value.by_blocker.is_empty() {
        return lines;
    }
    lines.extend([
        Line::from(""),
        Line::from(Span::styled(
            "DECISION-TIME L2 CONTEXT // INDEPENDENT WINDOWS // REPORT ONLY",
            app.theme.cyan,
        )),
    ]);
    for (blocker, group) in &value.by_blocker {
        for (side, evidence) in &group.by_side {
            lines.push(Line::from(Span::styled(
                format!("{} // {}", human_token(blocker), side.to_uppercase()),
                app.theme.gold,
            )));
            for minutes in [5_u16, 15, 30, 60] {
                if let Some(path) = evidence.horizons.get(&minutes) {
                    lines.push(Line::from(format!(
                        "{minutes:>2}M I{}  ALIGN {}  OPPOSE {}",
                        path.independent_resolved,
                        group_summary(&path.aligned),
                        group_summary(&path.opposed),
                    )));
                }
            }
        }
    }
    lines
}

fn stance_summary(
    value: &crate::backend_cohort_orderbook_opportunity::CohortSignalStanceCounts,
) -> String {
    format!(
        "A{} N{} O{} U{}",
        value.aligned, value.neutral, value.opposed, value.unavailable,
    )
}

fn group_summary(value: &CohortOrderbookGroup) -> String {
    let capture = &value.opportunity_capture;
    let net = capture
        .mean_close_after_estimated_friction_bps
        .map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"));
    let median = capture
        .median_close_after_estimated_friction_bps
        .map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"));
    let opi = value
        .mean_directional_opi
        .map_or_else(|| "N/A".into(), |number| format!("{number:+.2}"));
    format!(
        "N{} OPI{opi} ROB{} CLOSE{} REV{} AVG{net} MED{median}",
        value.paths,
        capture.robust_mfe_count,
        capture.cost_clearing_close_count,
        capture.reversed_after_cost_clear_count,
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;
    use crate::backend_cohort_orderbook_opportunity::{
        CohortEligibleSignalContext, CohortProviderPressureClock, CohortSignalStanceCounts,
    };

    #[test]
    fn renders_pressure_clock_as_data_quality_not_signal_confirmation() {
        let app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        let evidence = CohortProviderOrderbookOpportunity {
            by_blocker: BTreeMap::new(),
            pressure_clock: Some(CohortProviderPressureClock {
                pressure_unavailable_evaluations: 19,
                causal_book_available: 19,
                book_absent_or_stale: 0,
            }),
            eligible_signal_context: None,
        };

        let text = orderbook_lines(Some(&evidence), &app)
            .into_iter()
            .flat_map(|line| line.spans.into_iter())
            .map(|span| span.content.into_owned())
            .collect::<Vec<_>>()
            .join("");

        assert!(text.contains("PROVIDER PRESSURE CLOCK // REPORT ONLY"));
        assert!(text.contains("UNAVAILABLE 19 // CAUSAL BOOK 19 // ABSENT/STALE 0"));
        assert!(text.contains("BOOK PRESENT != SIGNAL CONFIRMED"));
    }

    #[test]
    fn renders_eligible_signal_pressure_and_regime_context_as_report_only() {
        let app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        let evidence = CohortProviderOrderbookOpportunity {
            by_blocker: BTreeMap::new(),
            pressure_clock: None,
            eligible_signal_context: Some(CohortEligibleSignalContext {
                eligible_signals: 14,
                pressure_stance: CohortSignalStanceCounts {
                    aligned: 5,
                    neutral: 0,
                    opposed: 9,
                    unavailable: 0,
                },
                state_5m_stance: CohortSignalStanceCounts {
                    aligned: 0,
                    neutral: 0,
                    opposed: 0,
                    unavailable: 14,
                },
                context_15m_stance: CohortSignalStanceCounts {
                    aligned: 0,
                    neutral: 0,
                    opposed: 0,
                    unavailable: 14,
                },
                executable_bbo_markouts: None,
            }),
        };

        let text = orderbook_lines(Some(&evidence), &app)
            .into_iter()
            .flat_map(|line| line.spans.into_iter())
            .map(|span| span.content.into_owned())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(text.contains("ELIGIBLE SIGNAL CONTEXT // REPORT ONLY"));
        assert!(text.contains("PRESSURE A5 N0 O9 U0"));
        assert!(text.contains("5M A0 N0 O0 U14 // 15M A0 N0 O0 U14"));
        assert!(text.contains("SIGNALS != ROUTES OR FILLS"));
    }
}
