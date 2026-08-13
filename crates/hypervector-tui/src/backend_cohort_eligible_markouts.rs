//! Strict projection of report-only eligible-signal executable-BBO markouts.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortEligibleBboMarkouts {
    pub(crate) horizons: BTreeMap<u16, CohortEpisodeBboHorizon>,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortEpisodeBboHorizon {
    pub(crate) provider_cadence_minutes: u16,
    pub(crate) eligible_onsets: usize,
    pub(crate) resolved_onsets: usize,
    pub(crate) independent_resolved: usize,
    pub(crate) all: CohortBboMarkoutGroup,
    pub(crate) long: CohortBboMarkoutGroup,
    pub(crate) short: CohortBboMarkoutGroup,
    pub(crate) pressure_aligned: CohortBboMarkoutGroup,
    pub(crate) pressure_opposed: CohortBboMarkoutGroup,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortBboMarkoutGroup {
    pub(crate) paths: usize,
    pub(crate) mean_after_modeled_friction_bps: Option<f64>,
    pub(crate) median_after_modeled_friction_bps: Option<f64>,
    pub(crate) mean_excluding_largest_after_modeled_friction_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverExecutableBboMarkoutsRaw {
    contract: ObserverBboContractRaw,
    maximum_book_lateness_ms: usize,
    horizons: BTreeMap<String, ObserverBboHorizonRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverBboContractRaw {
    report_only: bool,
    execution_authority: String,
    fills_assumed: bool,
    pnl_claimed: bool,
    entry_anchor: String,
    exit_anchor: String,
    entry_liquidity: String,
    exit_liquidity: String,
    funding_included: bool,
    thresholds_selected: bool,
    episode_cadence_source: String,
    episode_onset_definition: String,
}

#[derive(Debug, Deserialize)]
struct ObserverBboHorizonRaw {
    coverage: ObserverBboCoverageRaw,
    independent_resolved: usize,
    all: ObserverBboGroupRaw,
    by_side: BTreeMap<String, ObserverBboGroupRaw>,
    by_pressure_stance: BTreeMap<String, ObserverBboGroupRaw>,
    episode_onsets: ObserverBboEpisodeRaw,
}

#[derive(Debug, Deserialize)]
struct ObserverBboEpisodeRaw {
    status: String,
    provider_cadence_minutes: Option<u16>,
    reason: Option<String>,
    coverage: Option<ObserverBboCoverageRaw>,
    independent_resolved: Option<usize>,
    all: Option<ObserverBboGroupRaw>,
    by_side: Option<BTreeMap<String, ObserverBboGroupRaw>>,
    by_pressure_stance: Option<BTreeMap<String, ObserverBboGroupRaw>>,
}

#[derive(Debug, Deserialize)]
struct ObserverBboCoverageRaw {
    eligible_signals: usize,
    entry_matched: usize,
    entry_censored: usize,
    entry_gap: usize,
    resolved: usize,
    exit_censored: usize,
    exit_gap: usize,
    friction_contract_missing: usize,
}

#[derive(Debug, Deserialize)]
struct ObserverBboGroupRaw {
    paths: usize,
    friction_complete_paths: usize,
    mean_gross_bbo_bps: Option<f64>,
    median_gross_bbo_bps: Option<f64>,
    mean_after_fee_bps: Option<f64>,
    median_after_fee_bps: Option<f64>,
    mean_after_modeled_friction_bps: Option<f64>,
    median_after_modeled_friction_bps: Option<f64>,
    minimum_after_modeled_friction_bps: Option<f64>,
    maximum_after_modeled_friction_bps: Option<f64>,
    positive_after_modeled_friction_count: usize,
    positive_after_modeled_friction_rate: Option<f64>,
    mean_excluding_largest_after_modeled_friction_bps: Option<f64>,
}

pub(crate) fn project_eligible_bbo_markouts(
    raw: &ObserverExecutableBboMarkoutsRaw,
) -> Result<CohortEligibleBboMarkouts, String> {
    validate_contract(raw)?;
    let expected = BTreeSet::from(["5", "15", "30", "60"]);
    if raw
        .horizons
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>()
        != expected
    {
        return Err("eligible BBO markouts require exact 5/15/30/60 horizons".into());
    }
    let mut horizons = BTreeMap::new();
    for (label, horizon) in &raw.horizons {
        let minutes = label
            .parse::<u16>()
            .map_err(|_| "eligible BBO horizon must be positive minutes")?;
        validate_horizon(horizon)?;
        let episode = project_episode(&horizon.episode_onsets)?;
        horizons.insert(minutes, episode);
    }
    Ok(CohortEligibleBboMarkouts { horizons })
}

fn validate_contract(raw: &ObserverExecutableBboMarkoutsRaw) -> Result<(), String> {
    let value = &raw.contract;
    if !value.report_only
        || value.execution_authority != "none"
        || value.fills_assumed
        || value.pnl_claimed
        || value.entry_anchor != "first_book_at_or_after_signal_publication"
        || value.exit_anchor != "first_book_at_or_after_entry_plus_horizon"
        || value.entry_liquidity != "taker_bbo_cross"
        || value.exit_liquidity != "taker_bbo_cross"
        || value.funding_included
        || value.thresholds_selected
        || value.episode_cadence_source != "explicit_provider_timeframe_mapping"
        || value.episode_onset_definition
            != "first_signal_after_gap_direction_change_or_stream_boundary"
        || raw.maximum_book_lateness_ms == 0
    {
        return Err("eligible BBO markouts violate their report-only contract".into());
    }
    Ok(())
}

fn validate_horizon(raw: &ObserverBboHorizonRaw) -> Result<(), String> {
    validate_coverage(&raw.coverage)?;
    if raw.independent_resolved > raw.coverage.resolved {
        return Err("eligible BBO independent count exceeds resolved coverage".into());
    }
    validate_group(&raw.all)?;
    validate_group_map(&raw.by_side, &["long", "short"], raw.independent_resolved)?;
    validate_group_map(
        &raw.by_pressure_stance,
        &["aligned", "neutral", "opposed", "unavailable"],
        raw.independent_resolved,
    )?;
    if raw.all.paths != raw.independent_resolved {
        return Err("eligible BBO all-group count does not reconcile".into());
    }
    Ok(())
}

fn project_episode(raw: &ObserverBboEpisodeRaw) -> Result<CohortEpisodeBboHorizon, String> {
    if raw.status != "available" || raw.reason.is_some() {
        return Err("eligible BBO episode evidence is unavailable".into());
    }
    let cadence = raw
        .provider_cadence_minutes
        .filter(|value| *value > 0)
        .ok_or("eligible BBO episode cadence is invalid")?;
    let coverage = raw
        .coverage
        .as_ref()
        .ok_or("eligible BBO episode coverage missing")?;
    validate_coverage(coverage)?;
    let independent = raw
        .independent_resolved
        .ok_or("eligible BBO episode independent count missing")?;
    if independent > coverage.resolved {
        return Err("eligible BBO episode count exceeds resolved coverage".into());
    }
    let all = raw
        .all
        .as_ref()
        .ok_or("eligible BBO episode all-group missing")?;
    let sides = raw
        .by_side
        .as_ref()
        .ok_or("eligible BBO episode sides missing")?;
    let pressure = raw
        .by_pressure_stance
        .as_ref()
        .ok_or("eligible BBO episode pressure groups missing")?;
    validate_group(all)?;
    validate_group_map(sides, &["long", "short"], independent)?;
    validate_group_map(
        pressure,
        &["aligned", "neutral", "opposed", "unavailable"],
        independent,
    )?;
    if all.paths != independent {
        return Err("eligible BBO episode all-group count does not reconcile".into());
    }
    Ok(CohortEpisodeBboHorizon {
        provider_cadence_minutes: cadence,
        eligible_onsets: coverage.eligible_signals,
        resolved_onsets: coverage.resolved,
        independent_resolved: independent,
        all: project_group(all),
        long: project_group(&sides["long"]),
        short: project_group(&sides["short"]),
        pressure_aligned: project_group(&pressure["aligned"]),
        pressure_opposed: project_group(&pressure["opposed"]),
    })
}

fn validate_coverage(raw: &ObserverBboCoverageRaw) -> Result<(), String> {
    if raw.entry_matched + raw.entry_censored + raw.entry_gap != raw.eligible_signals
        || raw.resolved + raw.exit_censored + raw.exit_gap != raw.entry_matched
        || raw.friction_contract_missing > raw.resolved
    {
        return Err("eligible BBO coverage counts do not reconcile".into());
    }
    Ok(())
}

fn validate_group_map(
    raw: &BTreeMap<String, ObserverBboGroupRaw>,
    categories: &[&str],
    expected: usize,
) -> Result<(), String> {
    let required = categories.iter().copied().collect::<BTreeSet<_>>();
    if raw.keys().map(String::as_str).collect::<BTreeSet<_>>() != required {
        return Err("eligible BBO outcome categories are incomplete".into());
    }
    let total = raw.values().try_fold(0_usize, |total, group| {
        validate_group(group)?;
        total
            .checked_add(group.paths)
            .ok_or_else(|| "eligible BBO path count overflow".to_string())
    })?;
    if total != expected {
        return Err("eligible BBO outcome categories do not reconcile".into());
    }
    Ok(())
}

fn validate_group(raw: &ObserverBboGroupRaw) -> Result<(), String> {
    if raw.friction_complete_paths > raw.paths
        || raw.positive_after_modeled_friction_count > raw.friction_complete_paths
    {
        return Err("eligible BBO group counts do not reconcile".into());
    }
    validate_pair(raw.paths, raw.mean_gross_bbo_bps, raw.median_gross_bbo_bps)?;
    validate_pair(raw.paths, raw.mean_after_fee_bps, raw.median_after_fee_bps)?;
    validate_modeled_group(raw)?;
    Ok(())
}

fn validate_pair(count: usize, mean: Option<f64>, median: Option<f64>) -> Result<(), String> {
    if count == 0 && (mean.is_some() || median.is_some()) {
        return Err("empty eligible BBO group cannot carry means".into());
    }
    if count > 0 && (!finite(mean) || !finite(median)) {
        return Err("eligible BBO group requires finite means".into());
    }
    Ok(())
}

fn validate_modeled_group(raw: &ObserverBboGroupRaw) -> Result<(), String> {
    let values = [
        raw.mean_after_modeled_friction_bps,
        raw.median_after_modeled_friction_bps,
        raw.minimum_after_modeled_friction_bps,
        raw.maximum_after_modeled_friction_bps,
        raw.positive_after_modeled_friction_rate,
    ];
    if raw.friction_complete_paths == 0 && values.iter().any(Option::is_some) {
        return Err("empty eligible BBO friction group cannot carry outcomes".into());
    }
    if raw.friction_complete_paths > 0 && values.iter().any(|value| !finite(*value)) {
        return Err("eligible BBO friction outcomes must be finite".into());
    }
    if raw
        .positive_after_modeled_friction_rate
        .is_some_and(|value| !(0.0..=1.0).contains(&value))
    {
        return Err("eligible BBO positive rate must be within zero and one".into());
    }
    let excluded = raw.mean_excluding_largest_after_modeled_friction_bps;
    if (raw.friction_complete_paths > 1) != finite(excluded) {
        return Err("eligible BBO leave-largest mean has invalid coverage".into());
    }
    Ok(())
}

fn finite(value: Option<f64>) -> bool {
    value.is_some_and(f64::is_finite)
}

fn project_group(raw: &ObserverBboGroupRaw) -> CohortBboMarkoutGroup {
    CohortBboMarkoutGroup {
        paths: raw.paths,
        mean_after_modeled_friction_bps: raw.mean_after_modeled_friction_bps,
        median_after_modeled_friction_bps: raw.median_after_modeled_friction_bps,
        mean_excluding_largest_after_modeled_friction_bps: raw
            .mean_excluding_largest_after_modeled_friction_bps,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projects_episode_effective_bbo_outcomes() {
        let raw: ObserverExecutableBboMarkoutsRaw =
            serde_json::from_value(_wire(2)).expect("valid eligible BBO fixture");

        let projected = project_eligible_bbo_markouts(&raw).expect("valid evidence");
        let horizon = &projected.horizons[&60];

        assert_eq!(horizon.provider_cadence_minutes, 15);
        assert_eq!(horizon.independent_resolved, 2);
        assert_eq!(horizon.long.paths, 2);
        assert_eq!(horizon.short.paths, 0);
        assert_eq!(horizon.all.mean_after_modeled_friction_bps, Some(-6.8));
        assert_eq!(
            horizon
                .all
                .mean_excluding_largest_after_modeled_friction_bps,
            Some(-30.5)
        );
    }

    #[test]
    fn rejects_inflated_episode_independent_count() {
        let raw: ObserverExecutableBboMarkoutsRaw =
            serde_json::from_value(_wire(3)).expect("parseable invalid eligible BBO fixture");

        assert_eq!(
            project_eligible_bbo_markouts(&raw).unwrap_err(),
            "eligible BBO episode count exceeds resolved coverage"
        );
    }

    fn _wire(episode_independent: usize) -> serde_json::Value {
        let horizon = _horizon(episode_independent);
        serde_json::json!({
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "fills_assumed": false,
                "pnl_claimed": false,
                "entry_anchor": "first_book_at_or_after_signal_publication",
                "exit_anchor": "first_book_at_or_after_entry_plus_horizon",
                "entry_liquidity": "taker_bbo_cross",
                "exit_liquidity": "taker_bbo_cross",
                "funding_included": false,
                "thresholds_selected": false,
                "episode_cadence_source": "explicit_provider_timeframe_mapping",
                "episode_onset_definition":
                    "first_signal_after_gap_direction_change_or_stream_boundary"
            },
            "maximum_book_lateness_ms": 30_000,
            "horizons": {
                "5": horizon.clone(),
                "15": horizon.clone(),
                "30": horizon.clone(),
                "60": horizon
            }
        })
    }

    fn _horizon(episode_independent: usize) -> serde_json::Value {
        let all = _group(2, Some(-6.8), Some(-30.5));
        let long = _group(2, Some(-6.8), Some(-30.5));
        let empty = _group(0, None, None);
        let aligned = _group(1, Some(16.8), None);
        let opposed = _group(1, Some(-30.5), None);
        serde_json::json!({
            "coverage": _coverage(),
            "independent_resolved": 2,
            "all": all.clone(),
            "by_side": {"long": long.clone(), "short": empty.clone()},
            "by_pressure_stance": {
                "aligned": aligned.clone(), "neutral": empty.clone(),
                "opposed": opposed.clone(), "unavailable": empty.clone()
            },
            "episode_onsets": {
                "status": "available",
                "provider_cadence_minutes": 15,
                "coverage": _coverage(),
                "independent_resolved": episode_independent,
                "all": all,
                "by_side": {"long": long, "short": empty.clone()},
                "by_pressure_stance": {
                    "aligned": aligned, "neutral": empty.clone(),
                    "opposed": opposed, "unavailable": empty
                }
            }
        })
    }

    fn _coverage() -> serde_json::Value {
        serde_json::json!({
            "eligible_signals": 2, "entry_matched": 2,
            "entry_censored": 0, "entry_gap": 0, "resolved": 2,
            "exit_censored": 0, "exit_gap": 0,
            "friction_contract_missing": 0
        })
    }

    fn _group(
        paths: usize,
        mean: Option<f64>,
        excluding_largest: Option<f64>,
    ) -> serde_json::Value {
        serde_json::json!({
            "paths": paths,
            "friction_complete_paths": paths,
            "mean_gross_bbo_bps": mean,
            "median_gross_bbo_bps": mean,
            "mean_after_fee_bps": mean,
            "median_after_fee_bps": mean,
            "mean_after_modeled_friction_bps": mean,
            "median_after_modeled_friction_bps": mean,
            "minimum_after_modeled_friction_bps": mean,
            "maximum_after_modeled_friction_bps": mean,
            "positive_after_modeled_friction_count": if mean.is_some_and(|v| v > 0.0) { 1 } else { 0 },
            "positive_after_modeled_friction_rate": mean.map(|v| if v > 0.0 { 1.0 } else { 0.0 }),
            "mean_excluding_largest_after_modeled_friction_bps": excluding_largest
        })
    }
}
