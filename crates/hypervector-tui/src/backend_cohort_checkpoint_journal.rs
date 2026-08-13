//! Provider-level readiness and causal-path journal projection.

use std::collections::{BTreeMap, BTreeSet};

use crate::backend_cohort_checkpoint::{
    ObserverProviderPathEvidence, ObserverProviderReadiness, ObserverSignalOutcomesEvidence,
    ReadinessEvidence,
};
use crate::backend_cohort_checkpoint_values::{provider_identity, validated_paths};
use crate::backend_cohort_opportunity_capture::project_one_blocker_near_misses;
use crate::backend_cohort_orderbook_opportunity::{
    ObserverOrderbookOpportunityRaw, project_provider_orderbook, validate_eligible_signal_context,
    validate_pressure_clock,
};
use crate::backend_cohort_strategy_scorecard::{
    ObserverProviderScorecardEvidence, ObserverStrategyScorecardEvidence, execution_outcome_count,
    project_execution_performance, project_execution_performance_by_side,
    project_execution_performance_scope, project_repeatability_evidence,
    validate_strategy_scorecard,
};
use crate::cohort_observer_evidence::{
    CohortDirectionalResearchEvidence, CohortObserverPathEvidence, CohortObserverProviderEvidence,
};

pub(crate) fn provider_journal(
    readiness_evidence: &ReadinessEvidence,
    signal_outcomes: &ObserverSignalOutcomesEvidence,
    orderbook_opportunity: Option<&ObserverOrderbookOpportunityRaw>,
    strategy_scorecard: Option<&ObserverStrategyScorecardEvidence>,
    expected_execution_outcomes: Option<usize>,
) -> Result<Vec<CohortObserverProviderEvidence>, String> {
    let readiness = &readiness_evidence.by_provider_symbol;
    let outcomes = &signal_outcomes.by_provider_symbol;
    let keys = readiness
        .keys()
        .chain(outcomes.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    if let Some(scorecard) = strategy_scorecard {
        validate_strategy_scorecard(scorecard, &keys)?;
        if expected_execution_outcomes
            .is_some_and(|expected| execution_outcome_count(scorecard) != Ok(expected))
        {
            return Err("scorecard execution outcomes disagree with live execution".into());
        }
    }
    if let Some(orderbook) = orderbook_opportunity {
        validate_pressure_clock(orderbook, &keys)?;
        if let Some(context) = &orderbook.eligible_signal_context {
            validate_eligible_signal_context(context, &keys)?;
        }
    }
    keys.into_iter()
        .map(|key| {
            provider_journal_row(
                &key,
                readiness.get(&key),
                outcomes.get(&key),
                orderbook_opportunity.and_then(|value| value.by_provider_symbol.get(&key)),
                orderbook_opportunity
                    .and_then(|value| value.provider_pressure_clock.as_ref())
                    .and_then(|value| value.by_provider_symbol.get(&key)),
                orderbook_opportunity
                    .and_then(|value| value.eligible_signal_context.as_ref())
                    .and_then(|value| value.by_provider_symbol.get(&key)),
                strategy_scorecard.and_then(|scorecard| scorecard.by_provider_symbol.get(&key)),
            )
        })
        .collect()
}

fn provider_journal_row(
    key: &str,
    readiness: Option<&ObserverProviderReadiness>,
    outcome: Option<&ObserverProviderPathEvidence>,
    orderbook: Option<&crate::backend_cohort_orderbook_opportunity::ObserverProviderOrderbookRaw>,
    pressure_clock: Option<
        &crate::backend_cohort_orderbook_opportunity::ObserverProviderPressureClockRaw,
    >,
    signal_context: Option<
        &crate::backend_cohort_orderbook_opportunity::ObserverProviderSignalContextRaw,
    >,
    scorecard: Option<&ObserverProviderScorecardEvidence>,
) -> Result<CohortObserverProviderEvidence, String> {
    let (strategy_id, symbol) = provider_identity(key)?;
    if let Some(value) = readiness {
        validate_readiness(value)?;
    }
    let paths = outcome.map_or_else(|| Ok(BTreeMap::new()), provider_paths)?;
    let eligible_paths = evidence_class_paths(outcome, "eligible_signal")?;
    let readiness_paths = evidence_class_paths(outcome, "readiness_annotation")?;
    Ok(CohortObserverProviderEvidence {
        strategy_id,
        symbol,
        research_state: scorecard.map(|value| value.research_state.clone()),
        confidence: scorecard.map(|value| value.confidence.clone()),
        historical_cadence: scorecard.map(|value| value.historical_cadence.clone()),
        historical_summary: scorecard.map(|value| value.historical_summary.clone()),
        evidence_source: scorecard.map(|value| value.evidence_source.clone()),
        directional_research: scorecard.map_or_else(BTreeMap::new, |value| {
            value
                .directional_research
                .iter()
                .map(|(side, evidence)| {
                    (
                        side.clone(),
                        CohortDirectionalResearchEvidence {
                            side: evidence.side.clone(),
                            research_state: evidence.research_state.clone(),
                            confidence: evidence.confidence.clone(),
                            cadence: evidence.cadence.clone(),
                            summary: evidence.summary.clone(),
                            evidence_source: evidence.evidence_source.clone(),
                        },
                    )
                })
                .collect()
        }),
        forward_assessment: scorecard.map(|value| value.forward_assessment.clone()),
        execution_performance_scope: scorecard
            .map(project_execution_performance_scope)
            .transpose()?
            .flatten(),
        execution_performance: scorecard
            .map(project_execution_performance)
            .transpose()?
            .flatten(),
        execution_performance_by_side: scorecard.map_or_else(
            || Ok(BTreeMap::new()),
            project_execution_performance_by_side,
        )?,
        repeatability_evidence: scorecard
            .map(project_repeatability_evidence)
            .transpose()?
            .flatten(),
        latest_side: readiness.and_then(|value| value.latest_side.clone()),
        readiness_fraction: readiness.and_then(|value| value.latest_fraction),
        latest_reason: readiness.and_then(|value| value.latest_reason.clone()),
        latest_blockers: readiness
            .map(|value| value.latest_blockers.clone())
            .unwrap_or_default(),
        readiness_evaluations: readiness.map_or(0, |value| value.count),
        eligible_signals: outcome
            .and_then(|value| value.eligible_evaluations)
            .unwrap_or_else(|| readiness.map_or(0, |value| value.eligible)),
        paths,
        eligible_paths,
        readiness_paths,
        one_blocker_near_misses: project_one_blocker_near_misses(
            outcome.and_then(|value| value.one_blocker_near_misses.as_ref()),
        )?,
        orderbook_opportunity: project_provider_orderbook(
            orderbook,
            pressure_clock,
            signal_context,
        )?,
    })
}

fn evidence_class_paths(
    value: Option<&ObserverProviderPathEvidence>,
    evidence_class: &str,
) -> Result<BTreeMap<u16, CohortObserverPathEvidence>, String> {
    let Some(evidence) = value.and_then(|item| item.by_evidence_class.get(evidence_class)) else {
        return Ok(BTreeMap::new());
    };
    validated_paths(&evidence.horizons)
}

fn validate_readiness(value: &ObserverProviderReadiness) -> Result<(), String> {
    if value.eligible > value.count {
        return Err("observer provider eligible count exceeds evaluations".into());
    }
    if let Some(fraction) = value.latest_fraction
        && (!fraction.is_finite() || !(0.0..=1.0).contains(&fraction))
    {
        return Err("observer readiness fraction is outside [0,1]".into());
    }
    if let Some(side) = value.latest_side.as_deref()
        && !matches!(side, "long" | "short")
    {
        return Err("observer readiness side must be long or short".into());
    }
    if value
        .latest_reason
        .as_ref()
        .is_some_and(|reason| reason.trim().is_empty())
        || value
            .latest_blockers
            .iter()
            .any(|item| item.trim().is_empty())
    {
        return Err("observer readiness labels must be non-empty".into());
    }
    Ok(())
}

fn provider_paths(
    value: &ObserverProviderPathEvidence,
) -> Result<BTreeMap<u16, CohortObserverPathEvidence>, String> {
    if value
        .eligible_evaluations
        .zip(value.evaluations)
        .is_some_and(|(eligible, evaluations)| eligible > evaluations)
    {
        return Err("observer provider eligible paths exceed evaluations".into());
    }
    validated_paths(&value.horizons)
}
