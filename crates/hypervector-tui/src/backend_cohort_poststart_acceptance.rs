//! Strict projection of report-only seven-asset post-start monitoring verdicts.

use serde::Deserialize;

/// Operator-visible monitoring and attribution coverage for an exact version.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortPoststartAcceptance {
    pub version: String,
    pub accepted: bool,
    pub reasons: Vec<String>,
    pub expected_routes: usize,
    pub evaluated_routes: usize,
    pub routes_with_metrics: usize,
    pub open_positions: usize,
    pub fills: usize,
    pub costed_fills: usize,
    pub closed_trades: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct PoststartAcceptanceRaw {
    schema_version: String,
    contract: ContractRaw,
    accepted: bool,
    decision: String,
    reasons: Vec<String>,
    checks: ChecksRaw,
}

#[derive(Debug, Deserialize)]
struct ContractRaw {
    report_only: bool,
    execution_authority: String,
    automatic_pause: bool,
    automatic_retuning: bool,
    performance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct ChecksRaw {
    checkpoint_contract: CheckRaw,
    runtime_identity: CheckRaw,
    runtime_freshness: CheckRaw,
    runtime_execution_contracts: CheckRaw,
    provider_monitoring: ProviderMonitoringRaw,
    position_protection: PositionProtectionRaw,
    execution_attribution: ExecutionAttributionRaw,
    closed_lifecycle_integrity: ClosedLifecycleRaw,
    accounting_epoch: CheckRaw,
}

#[derive(Debug, Deserialize)]
struct CheckRaw {
    passed: bool,
    reasons: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct ProviderMonitoringRaw {
    passed: bool,
    reasons: Vec<String>,
    expected_routes: usize,
    evaluated_routes: usize,
    routes_with_metrics: usize,
}

#[derive(Debug, Deserialize)]
struct ExecutionAttributionRaw {
    passed: bool,
    reasons: Vec<String>,
    fills: usize,
    costed_fills: usize,
}

#[derive(Debug, Deserialize)]
struct PositionProtectionRaw {
    passed: bool,
    reasons: Vec<String>,
    open_positions: usize,
}

#[derive(Debug, Deserialize)]
struct ClosedLifecycleRaw {
    passed: bool,
    reasons: Vec<String>,
    closed_trades: usize,
}

pub(crate) fn project_poststart_acceptance(
    raw: Option<PoststartAcceptanceRaw>,
) -> Result<Option<CohortPoststartAcceptance>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate(&value)?;
    Ok(Some(CohortPoststartAcceptance {
        version: version_label(&value.schema_version)
            .expect("validated post-start schema")
            .into(),
        accepted: value.accepted,
        reasons: value.reasons,
        expected_routes: value.checks.provider_monitoring.expected_routes,
        evaluated_routes: value.checks.provider_monitoring.evaluated_routes,
        routes_with_metrics: value.checks.provider_monitoring.routes_with_metrics,
        open_positions: value.checks.position_protection.open_positions,
        fills: value.checks.execution_attribution.fills,
        costed_fills: value.checks.execution_attribution.costed_fills,
        closed_trades: value.checks.closed_lifecycle_integrity.closed_trades,
    }))
}

fn validate(value: &PoststartAcceptanceRaw) -> Result<(), String> {
    let provider = &value.checks.provider_monitoring;
    let position = &value.checks.position_protection;
    let execution = &value.checks.execution_attribution;
    let closed = &value.checks.closed_lifecycle_integrity;
    let generic = [
        &value.checks.checkpoint_contract,
        &value.checks.runtime_identity,
        &value.checks.runtime_freshness,
        &value.checks.runtime_execution_contracts,
        &value.checks.accounting_epoch,
    ];
    let all_passed = generic.iter().all(|check| check.passed)
        && provider.passed
        && position.passed
        && execution.passed
        && closed.passed;
    let verdict_shape = _verdict_matches(value, all_passed);
    let generic_shape = generic
        .iter()
        .all(|check| check.passed == check.reasons.is_empty());
    let provider_shape = provider.evaluated_routes <= provider.expected_routes
        && provider.routes_with_metrics <= provider.evaluated_routes
        && provider.passed == provider.reasons.is_empty();
    let position_shape = position.passed == position.reasons.is_empty();
    let execution_shape = execution.costed_fills <= execution.fills
        && (!execution.passed || execution.costed_fills == execution.fills)
        && execution.passed == execution.reasons.is_empty();
    let closed_shape = closed.passed == closed.reasons.is_empty();
    let valid = _contract_matches(value)
        && verdict_shape
        && _reasons_match(value)
        && generic_shape
        && provider_shape
        && position_shape
        && execution_shape
        && closed_shape;
    if !valid {
        return Err("post-start acceptance evidence is inconsistent".into());
    }
    Ok(())
}

fn _verdict_matches(value: &PoststartAcceptanceRaw, all_passed: bool) -> bool {
    let accepted =
        value.accepted && value.decision == "accepted" && value.reasons.is_empty() && all_passed;
    let rejected =
        !value.accepted && value.decision == "rejected" && !value.reasons.is_empty() && !all_passed;
    accepted || rejected
}

fn _contract_matches(value: &PoststartAcceptanceRaw) -> bool {
    let contract = &value.contract;
    version_label(&value.schema_version).is_some()
        && contract.report_only
        && contract.execution_authority == "none"
        && !contract.automatic_pause
        && !contract.automatic_retuning
        && !contract.performance_gate
}

fn version_label(schema: &str) -> Option<&'static str> {
    match schema {
        "v79_poststart_acceptance_v1" => Some("V79"),
        "v80_poststart_acceptance_v1" => Some("V80"),
        "v85_poststart_acceptance_v1" => Some("V85"),
        "v86_poststart_acceptance_v1" => Some("V86"),
        _ => None,
    }
}

fn _reasons_match(value: &PoststartAcceptanceRaw) -> bool {
    let checks = &value.checks;
    let groups = [
        &checks.checkpoint_contract.reasons,
        &checks.runtime_identity.reasons,
        &checks.runtime_freshness.reasons,
        &checks.runtime_execution_contracts.reasons,
        &checks.provider_monitoring.reasons,
        &checks.position_protection.reasons,
        &checks.execution_attribution.reasons,
        &checks.closed_lifecycle_integrity.reasons,
        &checks.accounting_epoch.reasons,
    ];
    value.reasons.iter().eq(groups.into_iter().flatten())
}
