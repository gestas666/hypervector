//! Display recorded provider exit targets without inferring an order or position side.

use crate::backend_cohort::CohortProviderEvaluation;

/// Name the provider signal using its recorded exit sides, including legacy uncertainty.
pub(crate) fn action_label(value: &CohortProviderEvaluation) -> String {
    let encoded = match value.decision_action.as_str() {
        "close_long" => Some("LONG"),
        "close_short" => Some("SHORT"),
        "close_open_position" => None,
        _ => return primary_with_exit(value),
    };
    let sides = match value.exit_sides.as_deref() {
        None => encoded,
        Some(sides) => recorded_sides(sides),
    };
    if encoded.is_some() && encoded != sides {
        return "EXIT SIDE N/A".into();
    }
    sides.map_or_else(|| "EXIT SIDE N/A".into(), |sides| format!("EXIT {sides}"))
}

fn primary_with_exit(value: &CohortProviderEvaluation) -> String {
    let primary = value.decision_action.to_uppercase();
    match value.exit_sides.as_deref() {
        Some(sides) if !sides.is_empty() => {
            let target = recorded_sides(sides).unwrap_or("SIDE N/A");
            format!("{primary} / EXIT {target}")
        }
        _ => primary,
    }
}

/// Fit both recorded signal directions in the regime matrix's compact column.
pub(crate) fn compact_action_label(value: &CohortProviderEvaluation) -> String {
    action_label(value)
        .replace("ENTER_LONG", "ENTER L")
        .replace("ENTER_SHORT", "ENTER S")
        .replace("LONG/SHORT", "L/S")
        .replace("EXIT LONG", "EXIT L")
        .replace("EXIT SHORT", "EXIT S")
        .replace(" / ", "/")
}

fn recorded_sides(sides: &[String]) -> Option<&'static str> {
    match sides {
        [side] if side == "long" => Some("LONG"),
        [side] if side == "short" => Some("SHORT"),
        [first, second]
            if (first == "long" && second == "short") || (first == "short" && second == "long") =>
        {
            Some("LONG/SHORT")
        }
        _ => None,
    }
}
