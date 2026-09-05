//! Regime-aware routing events projected from the authoritative cohort ledger.

use std::collections::BTreeSet;

use serde::Deserialize;

use super::{
    BackendCohortTelemetry, CohortProviderEvaluation, CohortSetupCoverage, parse_payload,
    retain_tail, validation,
};
use crate::backend_telemetry::LedgerRow;

const CANONICAL_REGIME_STRATEGY: &str = "canonical_regime_telemetry_v1";
const LEGACY_REGIME_STRATEGY: &str = "range_onset_bidirectional_v1";
const CANONICAL_NON_ACTION_REASON: &str = "telemetry_only_no_execution_authority";

/// One selected backend routing action.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortRoutingAction {
    #[serde(default)]
    pub observed_at: String,
    pub action: String,
    pub strategy_id: String,
    pub symbol: String,
    pub side: String,
    pub decision_time_ms: u64,
    pub reference_price: f64,
    #[serde(default)]
    pub target_anchor: Option<f64>,
    #[serde(default)]
    pub regime_alignment_score: Option<f64>,
    #[serde(default)]
    pub regime_alignment_stance: Option<String>,
    #[serde(default)]
    pub regime_decision_time_ms: Option<u64>,
    #[serde(default)]
    pub regime_alignment_basis: Option<String>,
    #[serde(default)]
    pub exit_reason: Option<String>,
}

/// One visible unexecuted intent and its exact backend reason.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortWithheldIntent {
    #[serde(default)]
    pub observed_at: String,
    pub strategy_id: String,
    pub symbol: String,
    pub side: String,
    pub decision_time_ms: u64,
    pub reference_price: f64,
    #[serde(default)]
    pub target_anchor: Option<f64>,
    pub source_reason: String,
    pub reason: String,
    #[serde(default)]
    pub regime_alignment_score: Option<f64>,
    #[serde(default)]
    pub regime_alignment_stance: Option<String>,
    #[serde(default)]
    pub regime_decision_time_ms: Option<u64>,
    #[serde(default)]
    pub regime_alignment_basis: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct CohortRoutingPayload {
    actions: Vec<CohortRoutingAction>,
    withheld: Vec<CohortWithheldIntent>,
    #[serde(default)]
    evaluations: Vec<CohortProviderEvaluation>,
    #[serde(default)]
    setup_coverage: Option<CohortSetupCoverage>,
}

#[derive(Debug, Clone, Deserialize)]
struct CanonicalRegimeContract {
    execution_authority: String,
    intents_emitted: bool,
    configured_route: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct CanonicalRegimePayload {
    contract: CanonicalRegimeContract,
    evaluations: Vec<CohortProviderEvaluation>,
}

pub(super) fn apply_routing_history(
    rows: &[&LedgerRow],
    cohort: &mut BackendCohortTelemetry,
) -> Result<(), String> {
    for row in rows.iter().filter(|row| row.action == "intent_routing") {
        let payload: CohortRoutingPayload = parse_payload(row)?;
        validate_preferences(&payload)?;
        if let Some(coverage) = payload.setup_coverage.as_ref() {
            validate_setup_coverage(cohort, coverage)?;
            cohort.setup_coverage = Some(coverage.clone());
        }
        append_outcomes(cohort, row, &payload);
        append_evaluations(cohort, row, payload.evaluations)?;
    }
    for row in rows
        .iter()
        .filter(|row| row.action == "canonical_regime_evaluations")
    {
        let payload: CanonicalRegimePayload = parse_payload(row)?;
        append_canonical_evaluations(cohort, row, payload)?;
    }
    retain_tail(&mut cohort.actions, 50);
    retain_tail(&mut cohort.withheld, 50);
    retain_tail(&mut cohort.regime_history, 240);
    Ok(())
}

fn validate_setup_coverage(
    cohort: &BackendCohortTelemetry,
    coverage: &CohortSetupCoverage,
) -> Result<(), String> {
    let expected = cohort
        .providers
        .iter()
        .flat_map(|provider| {
            provider
                .symbols
                .iter()
                .map(move |symbol| format!("{}|{symbol}", provider.strategy_id))
        })
        .collect::<BTreeSet<_>>();
    let missing = coverage
        .missing_provider_symbols
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    let counts_valid = coverage.expected_provider_symbols == expected.len()
        && coverage.observed_provider_symbols + missing.len() == expected.len();
    let status_valid = coverage.complete == missing.is_empty()
        && coverage.complete
            == (coverage.observed_provider_symbols == coverage.expected_provider_symbols);
    if missing.len() != coverage.missing_provider_symbols.len()
        || !missing.is_subset(&expected)
        || !counts_valid
        || !status_valid
    {
        return Err("cohort setup coverage is structurally invalid".into());
    }
    Ok(())
}

fn validate_preferences(payload: &CohortRoutingPayload) -> Result<(), String> {
    for action in &payload.actions {
        validation::validate_regime_preference(
            action.regime_alignment_score,
            action.regime_alignment_stance.as_deref(),
            action.regime_decision_time_ms,
            action.regime_alignment_basis.as_deref(),
        )?;
    }
    for intent in &payload.withheld {
        validation::validate_regime_preference(
            intent.regime_alignment_score,
            intent.regime_alignment_stance.as_deref(),
            intent.regime_decision_time_ms,
            intent.regime_alignment_basis.as_deref(),
        )?;
    }
    Ok(())
}

fn append_outcomes(
    cohort: &mut BackendCohortTelemetry,
    row: &LedgerRow,
    payload: &CohortRoutingPayload,
) {
    cohort
        .actions
        .extend(payload.actions.iter().cloned().map(|mut action| {
            action.observed_at.clone_from(&row.feed_ts);
            action
        }));
    cohort
        .withheld
        .extend(payload.withheld.iter().cloned().map(|mut intent| {
            intent.observed_at.clone_from(&row.feed_ts);
            intent
        }));
}

fn append_evaluations(
    cohort: &mut BackendCohortTelemetry,
    row: &LedgerRow,
    evaluations: Vec<CohortProviderEvaluation>,
) -> Result<(), String> {
    for mut evaluation in evaluations {
        evaluation.observed_at.clone_from(&row.feed_ts);
        validate_evaluation(cohort, &evaluation, false)?;
        if evaluation.strategy_id == LEGACY_REGIME_STRATEGY {
            append_regime_history(&mut cohort.regime_history, evaluation.clone());
        }
        upsert_evaluation(&mut cohort.evaluations, evaluation);
    }
    Ok(())
}

fn append_canonical_evaluations(
    cohort: &mut BackendCohortTelemetry,
    row: &LedgerRow,
    payload: CanonicalRegimePayload,
) -> Result<(), String> {
    let contract = payload.contract;
    if contract.execution_authority != "none"
        || contract.intents_emitted
        || contract.configured_route
        || cohort
            .providers
            .iter()
            .any(|provider| provider.strategy_id == CANONICAL_REGIME_STRATEGY)
    {
        return Err("canonical regime telemetry authority is invalid".into());
    }
    for mut evaluation in payload.evaluations {
        evaluation.observed_at.clone_from(&row.feed_ts);
        validate_evaluation(cohort, &evaluation, true)?;
        append_regime_history(&mut cohort.regime_history, evaluation.clone());
        upsert_evaluation(&mut cohort.evaluations, evaluation);
    }
    Ok(())
}

fn append_regime_history(
    history: &mut Vec<CohortProviderEvaluation>,
    candidate: CohortProviderEvaluation,
) {
    let duplicate = history.iter().any(|value| {
        value.symbol == candidate.symbol && value.decision_time_ms == candidate.decision_time_ms
    });
    if !duplicate {
        history.push(candidate);
    }
}

fn upsert_evaluation(
    evaluations: &mut Vec<CohortProviderEvaluation>,
    candidate: CohortProviderEvaluation,
) {
    let existing = evaluations.iter().position(|value| {
        value.strategy_id == candidate.strategy_id && value.symbol == candidate.symbol
    });
    if let Some(position) = existing {
        if candidate.decision_time_ms >= evaluations[position].decision_time_ms {
            evaluations[position] = candidate;
        }
    } else {
        evaluations.push(candidate);
    }
}

fn validate_evaluation(
    cohort: &BackendCohortTelemetry,
    evaluation: &CohortProviderEvaluation,
    canonical: bool,
) -> Result<(), String> {
    let readiness = &evaluation.readiness;
    let provider_known = if canonical {
        evaluation.strategy_id == CANONICAL_REGIME_STRATEGY
            && !evaluation.eligible
            && evaluation.decision_action == "regime_observation"
            && evaluation.backend_non_action_reason.as_deref() == Some(CANONICAL_NON_ACTION_REASON)
    } else {
        cohort
            .providers
            .iter()
            .any(|provider| provider.strategy_id == evaluation.strategy_id)
    };
    let sides_valid = evaluation
        .side
        .as_deref()
        .is_none_or(|side| matches!(side, "long" | "short"))
        && readiness
            .side
            .as_deref()
            .is_none_or(|side| matches!(side, "long" | "short"));
    let readiness_valid = readiness.readiness_fraction.is_finite()
        && (0.0..=1.0).contains(&readiness.readiness_fraction)
        && readiness.conditions_required > 0
        && readiness.conditions_met <= readiness.conditions_required;
    let text_valid = !evaluation.reason.is_empty()
        && !evaluation.decision_action.is_empty()
        && !readiness.indicators.is_empty();
    if !provider_known
        || !cohort.enabled_symbols.contains(&evaluation.symbol)
        || !sides_valid
        || !readiness_valid
        || !text_valid
        || !evaluation.reference_price.is_finite()
        || evaluation.reference_price <= 0.0
    {
        return Err("cohort provider evaluation is structurally invalid".into());
    }
    Ok(())
}
