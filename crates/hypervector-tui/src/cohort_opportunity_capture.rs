//! Compact visual projection of causal opportunity-capture diagnostics.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_opportunity_capture::CohortOneBlockerNearMisses;
use crate::cohort_observer_evidence::CohortObserverPathEvidence;
use crate::cohort_router_format::human_token;

pub(crate) fn path_capture_suffix(path: &CohortObserverPathEvidence) -> String {
    let Some(capture) = &path.opportunity_capture else {
        return String::new();
    };
    let after_cost = capture
        .mean_close_after_estimated_friction_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.1}"));
    let median = capture
        .median_close_after_estimated_friction_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.1}"));
    let range = distribution_range(capture);
    format!(
        "  IND COST {}/{} ROB {}/{} REV {} AVG{after_cost} MED{median} {range}",
        capture.cost_clearing_mfe_count,
        capture.resolved,
        capture.robust_mfe_count,
        capture.resolved,
        capture.reversed_after_cost_clear_count,
    )
}

fn distribution_range(
    capture: &crate::backend_cohort_opportunity_capture::CohortOpportunityCapture,
) -> String {
    match (
        capture.minimum_close_after_estimated_friction_bps,
        capture.maximum_close_after_estimated_friction_bps,
    ) {
        (Some(minimum), Some(maximum)) => format!("[{minimum:+.1},{maximum:+.1}]"),
        _ => "[N/A]".into(),
    }
}

pub(crate) fn one_blocker_lines<'a>(
    evidence: Option<&CohortOneBlockerNearMisses>,
    app: &App,
) -> Vec<Line<'a>> {
    let Some(value) = evidence.filter(|item| item.evaluations > 0) else {
        return Vec::new();
    };
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!(
                "ONE-BLOCKER NEAR MISSES // {} CAUSAL ANNOTATIONS // NO FILLS",
                value.evaluations
            ),
            app.theme.carry,
        )),
    ];
    for (blocker, group) in &value.by_blocker {
        lines.push(Line::from(Span::styled(
            format!("{}  //  N{}", human_token(blocker), group.evaluations),
            app.theme.gold,
        )));
        for minutes in [5_u16, 15, 30, 60] {
            if let Some(path) = group.paths.get(&minutes) {
                lines.push(Line::from(format!(
                    "{minutes:>2}M  R{}/I{}{}",
                    path.resolved,
                    path.independent,
                    path_capture_suffix(path),
                )));
            }
        }
        for (side, evidence) in &group.by_side {
            lines.push(Line::from(Span::styled(
                format!("  {} // N{}", side.to_uppercase(), evidence.evaluations),
                app.theme.cyan,
            )));
            for minutes in [5_u16, 15, 30, 60] {
                if let Some(path) = evidence.paths.get(&minutes) {
                    lines.push(Line::from(format!(
                        "    {minutes:>2}M R{}/I{}{}",
                        path.resolved,
                        path.independent,
                        path_capture_suffix(path),
                    )));
                }
            }
        }
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend_cohort_opportunity_capture::CohortOpportunityCapture;

    #[test]
    fn suffix_exposes_outlier_driven_mean() {
        let path = CohortObserverPathEvidence {
            resolved: 3,
            independent: 3,
            censored: 0,
            missing_data: 0,
            mean_directional_return_bps: Some(24.3),
            positive_directional_rate: Some(1.0),
            opportunity_capture: Some(CohortOpportunityCapture {
                resolved: 3,
                cost_clearing_mfe_count: 1,
                robust_mfe_count: 1,
                cost_clearing_close_count: 1,
                reversed_after_cost_clear_count: 1,
                mean_close_after_estimated_friction_bps: Some(11.287),
                median_close_after_estimated_friction_bps: Some(-4.849),
                minimum_close_after_estimated_friction_bps: Some(-5.390),
                maximum_close_after_estimated_friction_bps: Some(44.100),
            }),
        };

        assert!(path_capture_suffix(&path).contains("AVG+11.3 MED-4.8 [-5.4,+44.1]"));
    }
}
