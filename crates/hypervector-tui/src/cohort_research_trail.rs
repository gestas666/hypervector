//! Compact report-only post-soft trail presentation.

use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_cohort_post_soft_trail::CohortPostSoftTrailEvidence;

pub(crate) fn evidence(
    checkpoint: &CohortCheckpointTelemetry,
) -> Option<&CohortPostSoftTrailEvidence> {
    checkpoint
        .maximum_hold_decisions
        .as_ref()?
        .extension_outcomes
        .as_ref()?
        .post_soft_trail_challenger
        .as_ref()
}

pub(crate) fn summary_text(evidence: &CohortPostSoftTrailEvidence) -> String {
    let eligible = evidence
        .summary_by_giveback_bps
        .get(&20)
        .map_or(0, |value| value.eligible);
    let policies = [20_u16, 30, 40].map(|policy| {
        evidence.summary_by_giveback_bps.get(&policy).map_or_else(
            || format!("{policy}BPS N/A"),
            |value| {
                format!(
                    "{policy}BPS HIT{} ΔACT {}",
                    value.triggered,
                    signed_delta(value.trail_minus_actual_net_usd),
                )
            },
        )
    });
    format!(
        "POST-SOFT TRAIL // REPORT ONLY // N{eligible} | {} | {} | {}",
        policies[0], policies[1], policies[2]
    )
}

fn signed_delta(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

#[cfg(test)]
mod tests {
    use super::summary_text;
    use crate::backend_cohort_post_soft_trail::{
        CohortPostSoftTrailEvidence, CohortPostSoftTrailSummary,
    };
    use std::collections::BTreeMap;

    #[test]
    fn summary_names_report_scope_and_every_frozen_policy() {
        let evidence = CohortPostSoftTrailEvidence {
            summary_by_giveback_bps: BTreeMap::from([
                (20, summary(1, 0.04)),
                (30, summary(1, 0.06)),
                (40, summary(0, 0.00)),
            ]),
            latest_results: vec![],
        };

        assert_eq!(
            summary_text(&evidence),
            "POST-SOFT TRAIL // REPORT ONLY // N1 | 20BPS HIT1 ΔACT +$0.04 | 30BPS HIT1 ΔACT +$0.06 | 40BPS HIT0 ΔACT +$0.00",
        );
    }

    fn summary(triggered: usize, delta: f64) -> CohortPostSoftTrailSummary {
        CohortPostSoftTrailSummary {
            eligible: 1,
            triggered,
            not_triggered: 1 - triggered,
            estimated_net_pnl_usd: 0.0966 + delta,
            actual_net_pnl_usd: 0.0966,
            estimated_soft_net_pnl_usd: 0.2482,
            trail_minus_actual_net_usd: delta,
            trail_minus_soft_net_usd: delta - 0.1516,
        }
    }
}
