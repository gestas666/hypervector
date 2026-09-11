//! Entry-check evidence for the existing selected-setup inspector.

use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;

/// Describe only the selected exact route, preserving missing and legacy evidence.
pub fn summary_lines(
    checkpoint: &CohortCheckpointTelemetry,
    strategy_id: &str,
    symbol: &str,
) -> Vec<String> {
    let route = checkpoint.entry_deadlines.as_ref().and_then(|value| {
        value
            .by_provider_symbol
            .get(&format!("{strategy_id}|{symbol}"))
    });
    let Some(route) = route else {
        return vec!["ENTRY DEADLINE EVIDENCE UNAVAILABLE".into()];
    };
    let status = if route.sdk_dispatch_checks.is_some() {
        route.status.replace('_', " ").to_uppercase()
    } else {
        "LEGACY CHECKPOINT // CHECK STAGE UNAVAILABLE".into()
    };
    vec![
        "ENTRY DEADLINE // RUN AGGREGATE AT CHECKPOINT // REPORT ONLY".into(),
        status,
        format!(
            "LIMIT {} ms // ENTRY ACTIONS {} // STALE WITHHELD {}",
            route.maximum_entry_delay_ms, route.enter_actions, route.stale_entries_withheld
        ),
        format!(
            "CHECKS SDK {} // ADAPTER {} // ADMISSION/LEGACY {} // SDK OVER LIMIT {}",
            count(route.sdk_dispatch_checks),
            count(route.adapter_dispatch_checks),
            count(route.admission_or_legacy_checks),
            count(route.sdk_dispatches_over_limit)
        ),
        format!(
            "MAX RECORDED CHECK AGE {} // MIN HEADROOM {}",
            route
                .maximum_submission_age_ms
                .map_or_else(|| "N/A".into(), |v| format!("{v} ms")),
            route
                .minimum_submission_headroom_ms
                .map_or_else(|| "N/A".into(), |v| format!("{v} ms"))
        ),
        "SDK check precedes signing and network delivery; no venue-arrival claim.".into(),
    ]
}

fn count(value: Option<usize>) -> String {
    value.map_or_else(|| "N/A".into(), |number| number.to_string())
}
