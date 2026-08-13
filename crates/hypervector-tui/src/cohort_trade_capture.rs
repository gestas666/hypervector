//! Closed-trade capture-efficiency visual line.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_trade_reflections::CohortTradeReflection;

pub(crate) fn hold_capture_line<'a>(trade: &CohortTradeReflection, app: &App) -> Vec<Line<'a>> {
    let Some(capture) = trade.completed_hold_capture.as_ref() else {
        return Vec::new();
    };
    if capture.status != "resolved" {
        return vec![Line::from(format!(
            "HOLD CAPTURE {} // COMPLETED-CANDLE EVIDENCE INCOMPLETE",
            capture.status.to_uppercase()
        ))];
    }
    let ratio = capture
        .gross_mfe_capture_ratio
        .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0));
    let mut lines = vec![Line::from(vec![
        Span::styled("HOLD CAPTURE ", app.theme.carry),
        Span::raw(format!(
            "MFE {}  MAE {}  EXIT {}  CAPTURE {ratio}  GIVEBACK {}  BARS {}",
            bps(capture.maximum_favorable_excursion_bps),
            bps(capture.maximum_adverse_excursion_bps),
            signed_bps(capture.realized_gross_return_bps),
            bps(capture.peak_giveback_bps),
            capture.completed_bars.unwrap_or(0),
        )),
    ])];
    if let Some(text) = economic_capture_text(capture) {
        lines.push(Line::from(vec![
            Span::styled("AFTER COSTS ", app.theme.carry),
            Span::raw(text),
        ]));
    }
    lines
}

fn economic_capture_text(
    capture: &crate::backend_cohort_hold_capture::CohortCompletedHoldCapture,
) -> Option<String> {
    let outcome = match capture.economic_outcome.as_deref()? {
        "profitable_after_costs" => "PROFIT",
        "breakeven_after_costs" => "BREAKEVEN",
        "never_cleared_observed_cost_hurdle" => "NO COST CLEAR",
        "cleared_cost_hurdle_then_surrendered" => "CLEARED THEN LOST",
        "completed_path_unavailable" => "PATH UNAVAILABLE",
        _ => return None,
    };
    Some(format!(
        "ECON {outcome} // HURDLE {}  BEST NET {}  REALIZED {}  VENUE GROSS {}",
        signed_bps(capture.observed_cost_hurdle_bps),
        signed_bps(capture.maximum_net_excursion_bps),
        signed_bps(capture.realized_net_return_bps),
        signed_bps(capture.authoritative_gross_return_bps),
    ))
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1}bps"))
}

fn signed_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}bps"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend_cohort_hold_capture::CohortCompletedHoldCapture;

    #[test]
    fn economic_capture_names_a_trade_that_never_cleared_costs() {
        let capture = CohortCompletedHoldCapture {
            status: "resolved".into(),
            completed_bars: Some(12),
            maximum_favorable_excursion_bps: Some(8.0),
            maximum_adverse_excursion_bps: Some(2.0),
            realized_gross_return_bps: Some(5.0),
            gross_mfe_capture_ratio: Some(0.625),
            peak_giveback_bps: Some(3.0),
            observed_cost_hurdle_bps: Some(10.0),
            maximum_net_excursion_bps: Some(-2.0),
            realized_net_return_bps: Some(-5.0),
            authoritative_gross_return_bps: Some(5.0),
            price_gross_reconciliation_gap_bps: Some(0.0),
            economic_outcome: Some("never_cleared_observed_cost_hurdle".into()),
        };

        assert_eq!(
            economic_capture_text(&capture),
            Some(
                "ECON NO COST CLEAR // HURDLE +10.0bps  BEST NET -2.0bps  \
                 REALIZED -5.0bps  VENUE GROSS +5.0bps"
                    .into()
            )
        );
    }
}
