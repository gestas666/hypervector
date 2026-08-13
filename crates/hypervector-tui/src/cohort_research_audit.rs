//! Compact Screen 6 rendering for authoritative live audit evidence.

use ratatui::text::Line;

use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_cohort_live_audit::CohortLiveAuditStatus;

pub(crate) fn routing_line(checkpoint: &CohortCheckpointTelemetry) -> Line<'static> {
    Line::from(format!(
        "EVALUATIONS {}  //  INTENTS {}  //  ACTIONS {}  //  ELIGIBLE {}",
        count(checkpoint.readiness_evaluations),
        count(checkpoint.strategy_intents),
        count(checkpoint.routing_actions),
        count(checkpoint.eligible_signals),
    ))
}

pub(crate) fn audit_line(status: &CohortLiveAuditStatus) -> Line<'static> {
    Line::from(format!(
        "AUDIT ROWS {} // POLLS {} // CADENCE {} MED {} [{}..{}] // FAULTS {}",
        status.row_count,
        status.poll_cycles,
        seconds(status.poll_interval_mean_seconds),
        seconds(status.poll_interval_median_seconds),
        seconds(status.poll_interval_minimum_seconds),
        seconds(status.poll_interval_maximum_seconds),
        status.faults,
    ))
}

fn count(value: Option<usize>) -> String {
    value.map_or_else(|| "N/A".into(), |count| count.to_string())
}

fn seconds(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |seconds| format!("{seconds:.2}s"))
}
