//! Strict projection of report-only maximum-hold regime context evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use crate::backend_cohort_aligned_timer_extension::{
    CohortAlignedTimerExtensionEvidence, RawAlignedTimerExtensionEvidence,
    project_aligned_timer_extension,
};

const CONTEXTS: [&str; 4] = [
    "still_directionally_supported",
    "directionally_opposed",
    "mixed_or_transition",
    "unavailable",
];

/// Cumulative causal contexts observed at fixed maximum-hold exits.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTimerContextEvidence {
    pub timer_exits: usize,
    pub non_timer_exits: usize,
    pub still_directionally_supported: usize,
    pub directionally_opposed: usize,
    pub mixed_or_transition: usize,
    pub unavailable: usize,
    pub challenger_extend: Option<usize>,
    pub challenger_exit: Option<usize>,
    pub challenger_abstain: Option<usize>,
    pub challenger_five_minute: Option<CohortTimerExtensionHorizon>,
    pub aligned_zero_opposition_five_minute: Option<CohortAlignedTimerExtensionEvidence>,
    pub provider_symbols: Vec<CohortTimerProviderEvidence>,
}

/// Provider-symbol timer evidence kept separate from the portfolio aggregate.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTimerProviderEvidence {
    pub strategy_id: String,
    pub symbol: String,
    pub timer_exits: usize,
    pub non_timer_exits: usize,
    pub still_directionally_supported: usize,
    pub directionally_opposed: usize,
    pub mixed_or_transition: usize,
    pub unavailable: usize,
    pub challenger_extend: Option<usize>,
    pub challenger_exit: Option<usize>,
    pub challenger_abstain: Option<usize>,
    pub challenger_five_minute: Option<CohortTimerExtensionHorizon>,
}

/// Completed-candle gross projection for report-only timer extensions.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTimerExtensionHorizon {
    pub eligible_extensions: usize,
    pub resolved: usize,
    pub positive: usize,
    pub negative: usize,
    pub unchanged: usize,
    pub protective_stop_hits: usize,
    pub censored: usize,
    pub missing_data: usize,
    pub missing_protection: usize,
    pub incremental_gross_pnl_usd: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawTimerContextEvidence {
    contract: TimerContract,
    timer_exits: usize,
    non_timer_exits: usize,
    contexts: BTreeMap<String, RawContextSummary>,
    #[serde(default)]
    regime_aware_extension_challenger: Option<RawExtensionChallenger>,
    #[serde(default)]
    aligned_zero_opposition_extension_observer: Option<RawAlignedTimerExtensionEvidence>,
    #[serde(default)]
    provider_symbols: Vec<RawTimerProviderEvidence>,
}

#[derive(Debug, Deserialize)]
struct RawTimerProviderEvidence {
    strategy_id: String,
    symbol: String,
    timer_exits: usize,
    non_timer_exits: usize,
    contexts: BTreeMap<String, RawContextSummary>,
    #[serde(default)]
    regime_aware_extension_challenger: Option<RawExtensionChallenger>,
}

#[derive(Debug, Deserialize)]
struct TimerContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
}

#[derive(Debug, Deserialize)]
struct RawContextSummary {
    closed_trades: usize,
}

#[derive(Debug, Deserialize)]
struct RawExtensionChallenger {
    contract: TimerContract,
    decisions: BTreeMap<String, usize>,
    horizons: BTreeMap<String, RawExtensionHorizon>,
}

#[derive(Debug, Deserialize)]
struct RawExtensionHorizon {
    eligible_extensions: usize,
    resolved: usize,
    positive: usize,
    negative: usize,
    unchanged: usize,
    protective_stop_hits: usize,
    censored: usize,
    missing_data: usize,
    missing_protection: usize,
    incremental_gross_pnl_usd: f64,
}

pub(crate) fn project_timer_context(
    raw: Option<RawTimerContextEvidence>,
    expected_closed_trades: usize,
) -> Result<Option<CohortTimerContextEvidence>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let RawTimerContextEvidence {
        contract,
        timer_exits,
        non_timer_exits,
        contexts,
        regime_aware_extension_challenger,
        aligned_zero_opposition_extension_observer,
        provider_symbols,
    } = value;
    validate_contract(&contract)?;
    let summary = project_summary(
        timer_exits,
        non_timer_exits,
        expected_closed_trades,
        contexts,
        regime_aware_extension_challenger,
    )?;
    let providers = project_provider_symbols(provider_symbols, timer_exits, non_timer_exits)?;
    let aligned_zero_opposition_five_minute =
        project_aligned_timer_extension(aligned_zero_opposition_extension_observer, timer_exits)?;
    Ok(Some(CohortTimerContextEvidence {
        timer_exits,
        non_timer_exits,
        still_directionally_supported: summary.counts[0],
        directionally_opposed: summary.counts[1],
        mixed_or_transition: summary.counts[2],
        unavailable: summary.counts[3],
        challenger_extend: summary.challenger.as_ref().map(|value| value.0),
        challenger_exit: summary.challenger.as_ref().map(|value| value.1),
        challenger_abstain: summary.challenger.as_ref().map(|value| value.2),
        challenger_five_minute: summary.challenger.and_then(|value| value.3),
        aligned_zero_opposition_five_minute,
        provider_symbols: providers,
    }))
}

struct ProjectedTimerSummary {
    counts: [usize; 4],
    challenger: Option<ProjectedChallenger>,
}

fn project_provider_symbols(
    values: Vec<RawTimerProviderEvidence>,
    expected_timer_exits: usize,
    expected_non_timer_exits: usize,
) -> Result<Vec<CohortTimerProviderEvidence>, String> {
    let mut keys = BTreeSet::new();
    let mut providers = Vec::with_capacity(values.len());
    for value in values {
        let key = (value.strategy_id.clone(), value.symbol.clone());
        if key.0.trim().is_empty() || key.1.trim().is_empty() || !keys.insert(key) {
            return Err("timer-context provider identity is invalid or duplicated".into());
        }
        providers.push(project_provider(value)?);
    }
    if !providers.is_empty()
        && (providers
            .iter()
            .map(|value| value.timer_exits)
            .sum::<usize>()
            != expected_timer_exits
            || providers
                .iter()
                .map(|value| value.non_timer_exits)
                .sum::<usize>()
                != expected_non_timer_exits)
    {
        return Err("provider timer-context exits disagree with portfolio evidence".into());
    }
    Ok(providers)
}

fn project_provider(
    value: RawTimerProviderEvidence,
) -> Result<CohortTimerProviderEvidence, String> {
    let expected = value.timer_exits + value.non_timer_exits;
    let summary = project_summary(
        value.timer_exits,
        value.non_timer_exits,
        expected,
        value.contexts,
        value.regime_aware_extension_challenger,
    )?;
    Ok(CohortTimerProviderEvidence {
        strategy_id: value.strategy_id,
        symbol: value.symbol,
        timer_exits: value.timer_exits,
        non_timer_exits: value.non_timer_exits,
        still_directionally_supported: summary.counts[0],
        directionally_opposed: summary.counts[1],
        mixed_or_transition: summary.counts[2],
        unavailable: summary.counts[3],
        challenger_extend: summary.challenger.as_ref().map(|item| item.0),
        challenger_exit: summary.challenger.as_ref().map(|item| item.1),
        challenger_abstain: summary.challenger.as_ref().map(|item| item.2),
        challenger_five_minute: summary.challenger.and_then(|item| item.3),
    })
}

fn project_summary(
    timer_exits: usize,
    non_timer_exits: usize,
    expected_closed_trades: usize,
    contexts: BTreeMap<String, RawContextSummary>,
    challenger: Option<RawExtensionChallenger>,
) -> Result<ProjectedTimerSummary, String> {
    if timer_exits + non_timer_exits != expected_closed_trades {
        return Err("timer-context exits disagree with closed-trade evidence".into());
    }
    if contexts.len() != CONTEXTS.len() || CONTEXTS.iter().any(|key| !contexts.contains_key(*key)) {
        return Err("timer-context journal requires every known context".into());
    }
    let counts = CONTEXTS.map(|key| contexts[key].closed_trades);
    if counts.iter().sum::<usize>() != timer_exits {
        return Err("timer-context counts disagree with timer exits".into());
    }
    Ok(ProjectedTimerSummary {
        counts,
        challenger: project_challenger(challenger, timer_exits)?,
    })
}

type ProjectedChallenger = (usize, usize, usize, Option<CohortTimerExtensionHorizon>);

fn project_challenger(
    raw: Option<RawExtensionChallenger>,
    timer_exits: usize,
) -> Result<Option<ProjectedChallenger>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_contract(&value.contract)?;
    let actions = ["extend", "exit", "abstain"];
    if value.decisions.len() != actions.len()
        || actions
            .iter()
            .any(|action| !value.decisions.contains_key(*action))
    {
        return Err("timer extension challenger requires every decision".into());
    }
    if value.decisions.values().sum::<usize>() != timer_exits {
        return Err("timer extension decisions disagree with timer exits".into());
    }
    let extend = value.decisions["extend"];
    let mut five = None;
    for (raw_horizon, raw_value) in value.horizons {
        let horizon = raw_horizon
            .parse::<u16>()
            .map_err(|_| "timer extension horizon is invalid")?;
        let projected = project_horizon(raw_value, extend)?;
        if horizon == 5 {
            five = Some(projected);
        }
    }
    Ok(Some((
        extend,
        value.decisions["exit"],
        value.decisions["abstain"],
        five,
    )))
}

fn project_horizon(
    raw: RawExtensionHorizon,
    expected_extensions: usize,
) -> Result<CohortTimerExtensionHorizon, String> {
    if raw.eligible_extensions != expected_extensions
        || raw.resolved + raw.censored + raw.missing_data + raw.missing_protection
            != raw.eligible_extensions
        || raw.positive + raw.negative + raw.unchanged != raw.resolved
        || raw.protective_stop_hits > raw.resolved
        || !raw.incremental_gross_pnl_usd.is_finite()
    {
        return Err("timer extension horizon evidence is inconsistent".into());
    }
    Ok(CohortTimerExtensionHorizon {
        eligible_extensions: raw.eligible_extensions,
        resolved: raw.resolved,
        positive: raw.positive,
        negative: raw.negative,
        unchanged: raw.unchanged,
        protective_stop_hits: raw.protective_stop_hits,
        censored: raw.censored,
        missing_data: raw.missing_data,
        missing_protection: raw.missing_protection,
        incremental_gross_pnl_usd: raw.incremental_gross_pnl_usd,
    })
}

fn validate_contract(contract: &TimerContract) -> Result<(), String> {
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
    {
        return Err("timer-context contract is not report-only".into());
    }
    Ok(())
}
