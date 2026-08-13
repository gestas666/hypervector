//! Compact rendering of frozen forward execution contracts.

use crate::backend_cohort_forward_challenger::CohortForwardExecutionContract;

pub(crate) fn summary_text(contract: &CohortForwardExecutionContract) -> String {
    format!(
        "OPI {} ${:.0} FEE {:.2} STOP {:.0} {}M",
        contract.opi_cohort.to_uppercase(),
        contract.notional_usd,
        contract.taker_fee_rate * 10_000.0,
        contract.stop_proxy_bps,
        contract.horizon_minutes,
    )
}

pub(crate) fn contract_text(contract: &CohortForwardExecutionContract) -> String {
    format!(
        "CONTRACT {} // OPI {} // ${:.0} // FEE {:.2}bps // STOP {:.0}bps // TARGET {} // HOLD {}M // SPACE {}M",
        contract.symbol,
        contract.opi_cohort.to_uppercase(),
        contract.notional_usd,
        contract.taker_fee_rate * 10_000.0,
        contract.stop_proxy_bps,
        target(contract.target_proxy_bps),
        contract.horizon_minutes,
        contract.minimum_entry_spacing_minutes,
    )
}

pub(crate) fn timing_text(contract: &CohortForwardExecutionContract) -> String {
    format!(
        "TIMING CTX<={} // ENTRY<={} // EXIT<={} // CUTOFF {} // AUTH {}",
        duration(contract.maximum_context_age_ms),
        duration(contract.maximum_entry_delay_ms),
        duration(contract.maximum_exit_delay_ms),
        contract.cutoff_utc,
        contract.execution_authority.to_uppercase(),
    )
}

fn duration(value: Option<u64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |milliseconds| {
            if milliseconds % 1_000 == 0 {
                format!("{}s", milliseconds / 1_000)
            } else {
                format!("{milliseconds}ms")
            }
        },
    )
}

fn target(value: Option<f64>) -> String {
    value.map_or_else(|| "NONE".into(), |bps| format!("{bps:.0}bps"))
}
