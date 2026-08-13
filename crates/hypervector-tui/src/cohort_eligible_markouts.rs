//! Compact lines for episode-effective eligible-signal BBO evidence.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_eligible_markouts::{
    CohortBboMarkoutGroup, CohortEligibleBboMarkouts, CohortEpisodeBboHorizon,
};

pub(crate) fn markout_lines<'a>(
    value: Option<&CohortEligibleBboMarkouts>,
    app: &App,
) -> Vec<Line<'a>> {
    let Some(evidence) = value else {
        return Vec::new();
    };
    let mut lines = vec![Line::from(Span::styled(
        "BBO EPISODE ONSETS // REPORT ONLY",
        app.theme.cyan,
    ))];
    for minutes in [30_u16, 60] {
        if let Some(horizon) = evidence.horizons.get(&minutes) {
            lines.extend(horizon_lines(minutes, horizon));
        }
    }
    lines.push(Line::from(Span::styled(
        "TAKER BBO + MODELED FEES/SLIP // NO FILLS, PNL, FUNDING, OR ROUTING EFFECT",
        app.theme.muted,
    )));
    lines
}

fn horizon_lines(minutes: u16, value: &CohortEpisodeBboHorizon) -> [Line<'static>; 2] {
    let all = group(&value.all);
    [
        Line::from(format!(
            "{minutes}M CAD{} // ONSET I{}/R{}/E{} // NET {all}",
            value.provider_cadence_minutes,
            value.independent_resolved,
            value.resolved_onsets,
            value.eligible_onsets,
        )),
        Line::from(format!(
            "  SIDE L{} {} / S{} {} // PRESS A{} {} / O{} {}",
            value.long.paths,
            mean(&value.long),
            value.short.paths,
            mean(&value.short),
            value.pressure_aligned.paths,
            mean(&value.pressure_aligned),
            value.pressure_opposed.paths,
            mean(&value.pressure_opposed),
        )),
    ]
}

fn group(value: &CohortBboMarkoutGroup) -> String {
    format!(
        "{} MED {} EXMAX {}",
        mean(value),
        bps(value.median_after_modeled_friction_bps),
        bps(value.mean_excluding_largest_after_modeled_friction_bps),
    )
}

fn mean(value: &CohortBboMarkoutGroup) -> String {
    bps(value.mean_after_modeled_friction_bps)
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}bp"))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    #[test]
    fn renders_effective_count_side_coverage_and_leave_largest_result() {
        let app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        let group = |paths, mean, excluded| CohortBboMarkoutGroup {
            paths,
            mean_after_modeled_friction_bps: mean,
            median_after_modeled_friction_bps: mean,
            mean_excluding_largest_after_modeled_friction_bps: excluded,
        };
        let horizon = CohortEpisodeBboHorizon {
            provider_cadence_minutes: 15,
            eligible_onsets: 2,
            resolved_onsets: 2,
            independent_resolved: 2,
            all: group(2, Some(-6.88), Some(-30.54)),
            long: group(2, Some(-6.88), Some(-30.54)),
            short: group(0, None, None),
            pressure_aligned: group(1, Some(16.78), None),
            pressure_opposed: group(1, Some(-30.54), None),
        };
        let evidence = CohortEligibleBboMarkouts {
            horizons: BTreeMap::from([(30, horizon.clone()), (60, horizon)]),
        };

        let text = markout_lines(Some(&evidence), &app)
            .into_iter()
            .flat_map(|line| line.spans.into_iter())
            .map(|span| span.content.into_owned())
            .collect::<Vec<_>>()
            .join("\n");

        assert!(text.contains("BBO EPISODE ONSETS // REPORT ONLY"));
        assert!(text.contains("60M CAD15 // ONSET I2/R2/E2"));
        assert!(text.contains("NET -6.9bp MED -6.9bp EXMAX -30.5bp"));
        assert!(text.contains("SIDE L2 -6.9bp / S0 N/A"));
        assert!(text.contains("NO FILLS, PNL, FUNDING, OR ROUTING EFFECT"));
    }
}
