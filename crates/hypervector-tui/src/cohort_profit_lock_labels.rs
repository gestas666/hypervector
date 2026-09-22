//! Open-position profit-lock labels shared by compact and wide layouts.

use crate::backend_cohort_exit_plan::CohortOpenExitPlan;

#[derive(Clone, Copy)]
enum ProfitLockLabelMode {
    Compact,
    Detailed,
    Plan,
}

/// Format the compact open-position profit-lock contract.
pub(crate) fn compact_profit_lock_label(plan: &CohortOpenExitPlan) -> String {
    if plan.adaptive_exit_policy == "regime_book_profit_retention_v1" {
        return "PL:ADAPTIVE".into();
    }
    if plan.adaptive_exit_policy == "regime_flip_floor_retention_v2" {
        return "PL:ADAPTIVE2".into();
    }
    compact_profit_lock_contract_label(
        &plan.profit_lock_policy,
        plan.profit_lock_activation_bps,
        plan.profit_lock_floor_bps,
        plan.profit_lock_giveback_bps,
    )
}

/// Format compact profit-lock fields shared by checkpoint and ledger projections.
pub(crate) fn compact_profit_lock_contract_label(
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
) -> String {
    format_profit_lock(
        policy,
        activation,
        floor,
        giveback,
        ProfitLockLabelMode::Compact,
    )
}

/// Format a profit-lock token that fits the fixed-width execution-plan column.
pub(crate) fn plan_profit_lock_label(
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
) -> String {
    format_profit_lock(
        policy,
        activation,
        floor,
        giveback,
        ProfitLockLabelMode::Plan,
    )
}

/// Format the detailed open-position profit-lock contract.
pub(crate) fn profit_lock_label(plan: &CohortOpenExitPlan) -> String {
    if plan.adaptive_exit_policy == "regime_book_profit_retention_v1" {
        return "ADAPTIVE PROFIT FLOOR / REGIME / BOOK".into();
    }
    if plan.adaptive_exit_policy == "regime_flip_floor_retention_v2" {
        return "REGIME-FLIP RATCHET 0.5R / FLOOR +0.5R AFTER 2R / BREAK-EVEN STOP".into();
    }
    format_profit_lock(
        &plan.profit_lock_policy,
        plan.profit_lock_activation_bps,
        plan.profit_lock_floor_bps,
        plan.profit_lock_giveback_bps,
        ProfitLockLabelMode::Detailed,
    )
}

fn format_profit_lock(
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
    mode: ProfitLockLabelMode,
) -> String {
    if policy == "none" {
        return match mode {
            ProfitLockLabelMode::Compact => "PL:OFF",
            ProfitLockLabelMode::Detailed => "PROFIT LOCK OFF",
            ProfitLockLabelMode::Plan => "OFF",
        }
        .into();
    }
    if policy == "btc_hulk_delayed_component_floor_v1" {
        return match mode {
            ProfitLockLabelMode::Compact => "PL:DELAYED COMPONENT FLOOR",
            ProfitLockLabelMode::Detailed => "PROFIT LOCK DELAYED COMPONENT FLOOR",
            ProfitLockLabelMode::Plan => "DCF",
        }
        .into();
    }
    if policy == "btc_hulk_delayed_component_exit_v2" {
        return match mode {
            ProfitLockLabelMode::Compact => "PL:DELAYED COMPONENT EXIT",
            ProfitLockLabelMode::Detailed => "PROFIT LOCK FLOOR/REVERSAL CONTAINMENT",
            ProfitLockLabelMode::Plan => "DCE",
        }
        .into();
    }
    match (activation, floor, giveback) {
        (Some(a), Some(f), Some(g)) => match mode {
            ProfitLockLabelMode::Compact => format!("PL:{a:.0}/{f:.0}/{g:.0}"),
            ProfitLockLabelMode::Detailed => {
                format!("PROFIT LOCK ON ACT {a:.1}bps FLOOR {f:.1}bps GIVEBACK {g:.1}bps")
            }
            ProfitLockLabelMode::Plan => "TR".into(),
        },
        _ => match mode {
            ProfitLockLabelMode::Compact => "PL:INVALID",
            ProfitLockLabelMode::Detailed => "PROFIT LOCK INVALID",
            ProfitLockLabelMode::Plan => "!",
        }
        .into(),
    }
}

#[cfg(test)]
mod tests {
    use super::{ProfitLockLabelMode, format_profit_lock};

    #[test]
    fn open_profit_lock_labels_preserve_exact_parameters() {
        let values = (Some(25.0), Some(8.0), Some(6.0));
        assert_eq!(
            format_profit_lock(
                "completed_bar_trailing",
                values.0,
                values.1,
                values.2,
                ProfitLockLabelMode::Compact,
            ),
            "PL:25/8/6",
        );
        assert_eq!(
            format_profit_lock(
                "completed_bar_trailing",
                values.0,
                values.1,
                values.2,
                ProfitLockLabelMode::Detailed,
            ),
            "PROFIT LOCK ON ACT 25.0bps FLOOR 8.0bps GIVEBACK 6.0bps",
        );
        assert_eq!(
            format_profit_lock(
                "btc_hulk_delayed_component_floor_v1",
                None,
                None,
                None,
                ProfitLockLabelMode::Compact,
            ),
            "PL:DELAYED COMPONENT FLOOR",
        );
        assert_eq!(
            format_profit_lock(
                "btc_hulk_delayed_component_floor_v1",
                None,
                None,
                None,
                ProfitLockLabelMode::Detailed,
            ),
            "PROFIT LOCK DELAYED COMPONENT FLOOR",
        );
        assert_eq!(
            format_profit_lock(
                "btc_hulk_delayed_component_exit_v2",
                None,
                None,
                None,
                ProfitLockLabelMode::Compact,
            ),
            "PL:DELAYED COMPONENT EXIT",
        );
        assert_eq!(
            format_profit_lock(
                "btc_hulk_delayed_component_exit_v2",
                None,
                None,
                None,
                ProfitLockLabelMode::Detailed,
            ),
            "PROFIT LOCK FLOOR/REVERSAL CONTAINMENT",
        );
    }
}

#[test]
fn adaptive_exit_is_visible_as_active_profit_protection() {
    let plan = CohortOpenExitPlan {
        adaptive_exit_policy: "regime_book_profit_retention_v1".into(),
        profit_lock_policy: "none".into(),
        ..Default::default()
    };
    assert_eq!(compact_profit_lock_label(&plan), "PL:ADAPTIVE");
    assert_eq!(
        profit_lock_label(&plan),
        "ADAPTIVE PROFIT FLOOR / REGIME / BOOK"
    );
}
