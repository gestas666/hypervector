//! Typed, report-only entry-check evidence from the Python routing audit.

use std::collections::BTreeMap;

use serde::Deserialize;

/// Run aggregates retaining legacy versus named check-stage coverage.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortEntryDeadlines {
    contract: DeadlineContract,
    pub enter_actions: usize,
    pub submitted_entries: usize,
    pub sdk_dispatch_checks: Option<usize>,
    pub stale_entries_withheld: usize,
    pub by_provider_symbol: BTreeMap<String, EntryDeadlineRoute>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
struct DeadlineContract {
    report_only: bool,
    execution_authority: String,
    automatic_live_change: bool,
    automatic_pause: bool,
    entry_enforcement_changed: bool,
}

/// One exact provider-symbol's recorded checks, rather than its latest decision.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct EntryDeadlineRoute {
    pub maximum_entry_delay_ms: u64,
    pub enter_actions: usize,
    pub submitted_entries: usize,
    pub sdk_dispatch_checks: Option<usize>,
    pub sdk_dispatches_over_limit: Option<usize>,
    pub adapter_dispatch_checks: Option<usize>,
    pub admission_or_legacy_checks: Option<usize>,
    pub stale_entries_withheld: usize,
    pub submitted_entries_over_limit: usize,
    pub maximum_submission_age_ms: Option<u64>,
    pub minimum_submission_headroom_ms: Option<i64>,
    pub maximum_withheld_submission_age_ms: Option<u64>,
    pub status: String,
}

pub(crate) fn project(
    value: Option<CohortEntryDeadlines>,
) -> Result<Option<CohortEntryDeadlines>, String> {
    if let Some(evidence) = &value {
        validate(evidence)?;
    }
    Ok(value)
}

fn validate(value: &CohortEntryDeadlines) -> Result<(), String> {
    let contract = &value.contract;
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.automatic_live_change
        || contract.automatic_pause
        || contract.entry_enforcement_changed
        || value.by_provider_symbol.is_empty()
    {
        return Err("entry deadline evidence violates its report-only contract".into());
    }
    for (key, route) in &value.by_provider_symbol {
        let Some((strategy, symbol)) = key.split_once('|') else {
            return Err("entry deadline route lacks its provider-symbol identity".into());
        };
        if strategy.is_empty()
            || symbol.is_empty()
            || symbol.contains('|')
            || key.chars().any(char::is_control)
        {
            return Err("entry deadline route identity is malformed".into());
        }
        validate_route(route)?;
        if route.sdk_dispatch_checks.is_some() != value.sdk_dispatch_checks.is_some() {
            return Err("entry deadline stage schema differs across route and aggregate".into());
        }
    }
    let routes = &value.by_provider_symbol;
    if sum(routes.values().map(|r| r.enter_actions))? != value.enter_actions
        || sum(routes.values().map(|r| r.submitted_entries))? != value.submitted_entries
        || sum(routes.values().map(|r| r.stale_entries_withheld))? != value.stale_entries_withheld
    {
        return Err("entry deadline aggregate counts do not reconcile".into());
    }
    if let Some(expected) = value.sdk_dispatch_checks
        && sum(routes.values().filter_map(|r| r.sdk_dispatch_checks))? != expected
    {
        return Err("entry deadline SDK counts do not reconcile".into());
    }
    Ok(())
}

fn sum(mut values: impl Iterator<Item = usize>) -> Result<usize, String> {
    values.try_fold(0usize, |total, value| {
        total
            .checked_add(value)
            .ok_or_else(|| "entry deadline count overflow".into())
    })
}

fn validate_route(route: &EntryDeadlineRoute) -> Result<(), String> {
    if route.maximum_entry_delay_ms == 0
        || route.submitted_entries > route.enter_actions
        || route.submitted_entries_over_limit > route.submitted_entries
        || ((route.submitted_entries_over_limit > 0)
            != route
                .maximum_submission_age_ms
                .is_some_and(|age| age > route.maximum_entry_delay_ms))
        || (route.maximum_submission_age_ms.is_some() != (route.submitted_entries > 0))
        || (route.maximum_withheld_submission_age_ms.is_some()
            != (route.stale_entries_withheld > 0))
    {
        return Err("entry deadline route counts or extrema are inconsistent".into());
    }
    match (
        route.maximum_submission_age_ms,
        route.minimum_submission_headroom_ms,
    ) {
        (Some(age), Some(headroom)) => {
            if i128::from(route.maximum_entry_delay_ms) - i128::from(age) != i128::from(headroom) {
                return Err("entry deadline recorded age and headroom disagree".into());
            }
        }
        (None, None) => {}
        _ => return Err("entry deadline recorded check lacks age or headroom".into()),
    }
    validate_stages(route)
}

fn validate_stages(route: &EntryDeadlineRoute) -> Result<(), String> {
    match (
        route.sdk_dispatch_checks,
        route.sdk_dispatches_over_limit,
        route.adapter_dispatch_checks,
        route.admission_or_legacy_checks,
    ) {
        (None, None, None, None) => {
            if ![
                "submission_contract_enforced",
                "executed_submission_contract_breach",
                "potential_submission_contract_breach",
                "measured_no_action_breach",
            ]
            .contains(&route.status.as_str())
            {
                return Err("legacy entry deadline evidence has an unsupported status".into());
            }
        }
        (Some(sdk), Some(late), Some(adapter), Some(admission)) => {
            if sum([sdk, adapter, admission].into_iter())? != route.submitted_entries
                || late > sdk
                || late > route.submitted_entries_over_limit
            {
                return Err("entry deadline stage counts do not reconcile".into());
            }
            validate_named_status(route, sdk, late, adapter)?;
        }
        _ => return Err("entry deadline stage counters are incomplete".into()),
    }
    Ok(())
}

fn validate_named_status(
    route: &EntryDeadlineRoute,
    sdk: usize,
    late: usize,
    adapter: usize,
) -> Result<(), String> {
    let expected = if late > 0 {
        "executed_submission_contract_breach"
    } else if route.submitted_entries_over_limit > 0 {
        "recorded_check_contract_breach"
    } else if sdk > 0 && sdk == route.enter_actions {
        "sdk_dispatch_contract_observed"
    } else if adapter > 0 && adapter == route.enter_actions {
        "adapter_dispatch_check_observed"
    } else if sdk > 0 || adapter > 0 {
        "mixed_submission_boundaries_observed"
    } else if route.submitted_entries > 0 {
        "admission_check_observed"
    } else if route.stale_entries_withheld > 0 {
        "stale_entry_withholding_observed"
    } else if matches!(
        route.status.as_str(),
        "potential_submission_contract_breach" | "measured_no_action_breach"
    ) {
        return Ok(());
    } else {
        return Err("entry deadline check status lacks recorded evidence".into());
    };
    if route.status != expected {
        return Err("entry deadline check status contradicts its recorded counts".into());
    }
    Ok(())
}
