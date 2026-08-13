//! Cross-source identity validation for checkpoint and authoritative ledger data.

use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_telemetry::BackendTelemetrySnapshot;

pub(crate) fn validate_checkpoint_identity(
    backend: &BackendTelemetrySnapshot,
    checkpoint: &CohortCheckpointTelemetry,
) -> Result<(), String> {
    match checkpoint.analysis_mode.as_deref() {
        Some("live_execution") => validate_live_identity(backend, checkpoint),
        Some("forward_observer") => match_identity(
            "run",
            backend.run_id.as_deref(),
            checkpoint.run_id.as_deref(),
        ),
        _ => Err("checkpoint analysis mode cannot be identity-bound".into()),
    }
}

fn validate_live_identity(
    backend: &BackendTelemetrySnapshot,
    checkpoint: &CohortCheckpointTelemetry,
) -> Result<(), String> {
    match_identity(
        "run",
        backend.run_id.as_deref(),
        checkpoint.run_id.as_deref(),
    )?;
    match_identity(
        "profile",
        backend.profile_id.as_deref(),
        checkpoint.profile_id.as_deref(),
    )?;
    match_identity(
        "profile fingerprint",
        backend.profile_fingerprint.as_deref(),
        checkpoint.profile_fingerprint.as_deref(),
    )
}

fn match_identity(
    label: &str,
    backend: Option<&str>,
    checkpoint: Option<&str>,
) -> Result<(), String> {
    let backend = backend.filter(|value| !value.is_empty()).ok_or_else(|| {
        format!("backend {label} identity is unavailable; checkpoint merge refused")
    })?;
    let checkpoint = checkpoint
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            format!("checkpoint {label} identity is unavailable; checkpoint merge refused")
        })?;
    if backend != checkpoint {
        return Err(format!(
            "checkpoint {label} identity differs from authoritative ledger"
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn backend() -> BackendTelemetrySnapshot {
        let mut value = BackendTelemetrySnapshot::disconnected("fixture");
        value.run_id = Some("run-a".into());
        value.profile_id = Some("profile-a".into());
        value.profile_fingerprint = Some("fingerprint-a".into());
        value
    }

    fn checkpoint() -> CohortCheckpointTelemetry {
        CohortCheckpointTelemetry {
            available: true,
            analysis_mode: Some("live_execution".into()),
            run_id: Some("run-a".into()),
            profile_id: Some("profile-a".into()),
            profile_fingerprint: Some("fingerprint-a".into()),
            ..CohortCheckpointTelemetry::default()
        }
    }

    #[test]
    fn accepts_exact_live_identity() {
        validate_checkpoint_identity(&backend(), &checkpoint()).expect("exact identity");
    }

    #[test]
    fn rejects_fresh_checkpoint_from_another_run() {
        let mut foreign = checkpoint();
        foreign.run_id = Some("run-b".into());

        let error = validate_checkpoint_identity(&backend(), &foreign)
            .expect_err("foreign checkpoint accepted");

        assert!(error.contains("run identity differs"));
    }

    #[test]
    fn rejects_success_shaped_live_checkpoint_without_identity() {
        let missing = CohortCheckpointTelemetry {
            available: true,
            analysis_mode: Some("live_execution".into()),
            ..CohortCheckpointTelemetry::default()
        };

        let error = validate_checkpoint_identity(&backend(), &missing)
            .expect_err("identity-free checkpoint accepted");

        assert!(error.contains("checkpoint run identity is unavailable"));
    }
}
