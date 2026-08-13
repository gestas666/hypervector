//! Open-position profit-lock labels shared by compact and wide layouts.

use crate::backend_cohort_exit_plan::CohortOpenExitPlan;

/// Format the compact open-position profit-lock contract.
pub(crate) fn compact_profit_lock_label(plan: &CohortOpenExitPlan) -> String {
    format_profit_lock(
        &plan.profit_lock_policy,
        plan.profit_lock_activation_bps,
        plan.profit_lock_floor_bps,
        plan.profit_lock_giveback_bps,
        true,
    )
}

/// Format the detailed open-position profit-lock contract.
pub(crate) fn profit_lock_label(plan: &CohortOpenExitPlan) -> String {
    format_profit_lock(
        &plan.profit_lock_policy,
        plan.profit_lock_activation_bps,
        plan.profit_lock_floor_bps,
        plan.profit_lock_giveback_bps,
        false,
    )
}

fn format_profit_lock(
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
    compact: bool,
) -> String {
    if policy == "none" {
        return if compact { "PL:OFF" } else { "PROFIT LOCK OFF" }.into();
    }
    match (activation, floor, giveback, compact) {
        (Some(a), Some(f), Some(g), true) => format!("PL:{a:.0}/{f:.0}/{g:.0}"),
        (Some(a), Some(f), Some(g), false) => {
            format!("PROFIT LOCK ON ACT {a:.1}bps FLOOR {f:.1}bps GIVEBACK {g:.1}bps")
        }
        (_, _, _, true) => "PL:INVALID".into(),
        _ => "PROFIT LOCK INVALID".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::format_profit_lock;

    #[test]
    fn open_profit_lock_labels_preserve_exact_parameters() {
        let values = (Some(25.0), Some(8.0), Some(6.0));
        assert_eq!(
            format_profit_lock("completed_bar_trailing", values.0, values.1, values.2, true),
            "PL:25/8/6",
        );
        assert_eq!(
            format_profit_lock(
                "completed_bar_trailing",
                values.0,
                values.1,
                values.2,
                false
            ),
            "PROFIT LOCK ON ACT 25.0bps FLOOR 8.0bps GIVEBACK 6.0bps",
        );
    }
}
