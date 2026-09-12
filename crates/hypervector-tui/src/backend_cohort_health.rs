//! Cohort health derives from backend heartbeat evidence, independently of other writes.

use std::time::{Duration, SystemTime};

use chrono::{DateTime, Utc};

use crate::backend_telemetry::{BackendConnectionState, BackendTelemetrySnapshot, LedgerRow};

/// Latest backend heartbeat, preserving missing status and its actual observation clock.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHeartbeat {
    pub observed_at: String,
    pub status: Option<String>,
}

/// Retain only the latest actual heartbeat row from this run.
pub(crate) fn project_heartbeat(rows: &[&LedgerRow]) -> Option<CohortHeartbeat> {
    rows.iter()
        .rev()
        .find(|row| row.action == "heartbeat")
        .map(|row| CohortHeartbeat {
            observed_at: row.feed_ts.clone(),
            status: row
                .extra
                .get("status")
                .and_then(|value| value.as_str())
                .map(str::to_owned),
        })
}

/// Retain terminal fault evidence for the current run even after later writes.
pub(crate) fn project_fault(rows: &[&LedgerRow]) -> Option<String> {
    rows.iter()
        .rev()
        .find(|row| row.action == "runtime_fault")
        .map(|row| row.feed_ts.clone())
}

/// A subsequent actual poll supersedes a normally stopped observer of the same run.
pub(crate) fn project_stopped(rows: &[&LedgerRow]) -> Option<String> {
    rows.iter()
        .rev()
        .find(|row| matches!(row.action.as_str(), "heartbeat" | "runtime_stopped"))
        .filter(|row| row.action == "runtime_stopped")
        .map(|row| row.feed_ts.clone())
}

/// Classify current file-backed cohort health without granting execution authority.
pub(crate) fn apply(
    mut snapshot: BackendTelemetrySnapshot,
    now: SystemTime,
    inactivity_limit: Duration,
) -> BackendTelemetrySnapshot {
    if snapshot.connection != BackendConnectionState::Connected {
        return snapshot;
    }
    let issue = if snapshot.cohort.runtime_fault_at.is_some() {
        Some((
            BackendConnectionState::Error,
            "cohort backend reported a terminal runtime fault".into(),
        ))
    } else if let Some(stopped_at) = snapshot.cohort.runtime_stopped_at.as_deref() {
        Some(stopped_issue(stopped_at, now))
    } else {
        heartbeat_issue(snapshot.cohort.heartbeat.as_ref(), now, inactivity_limit)
    };
    if let Some((state, message)) = issue {
        snapshot.connection = state;
        snapshot.status_message = message;
    }
    snapshot
}

fn stopped_issue(stopped_at: &str, now: SystemTime) -> (BackendConnectionState, String) {
    match DateTime::parse_from_rfc3339(stopped_at) {
        Err(_) => (
            BackendConnectionState::Error,
            "backend stop timestamp invalid".into(),
        ),
        Ok(at) if at > DateTime::<Utc>::from(now) => (
            BackendConnectionState::Error,
            "backend stop timestamp is in the future; clock health unknown".into(),
        ),
        Ok(_) => (
            BackendConnectionState::Stale,
            "cohort backend reported normal stop".into(),
        ),
    }
}

fn heartbeat_issue(
    heartbeat: Option<&CohortHeartbeat>,
    now: SystemTime,
    inactivity_limit: Duration,
) -> Option<(BackendConnectionState, String)> {
    let Some(heartbeat) = heartbeat else {
        return Some((
            BackendConnectionState::Stale,
            "cohort heartbeat unavailable; process health unknown".into(),
        ));
    };
    let observed = match DateTime::parse_from_rfc3339(&heartbeat.observed_at) {
        Ok(observed) => observed,
        Err(_) => {
            return Some((
                BackendConnectionState::Error,
                "cohort heartbeat timestamp invalid".into(),
            ));
        }
    };
    let age = DateTime::<Utc>::from(now).signed_duration_since(observed);
    if age < chrono::Duration::zero() {
        return Some((
            BackendConnectionState::Error,
            "cohort heartbeat timestamp is in the future; clock health unknown".into(),
        ));
    }
    if age.to_std().is_ok_and(|age| age > inactivity_limit) {
        return Some((
            BackendConnectionState::Stale,
            format!(
                "cohort heartbeat inactive for more than {}s; process health unknown",
                inactivity_limit.as_secs()
            ),
        ));
    }
    status_issue(heartbeat.status.as_deref())
}

fn status_issue(status: Option<&str>) -> Option<(BackendConnectionState, String)> {
    match status {
        Some("running") => None,
        Some("degraded") => Some((
            BackendConnectionState::Stale,
            "cohort heartbeat reports degraded polling".into(),
        )),
        Some("stopped") => Some((
            BackendConnectionState::Stale,
            "cohort heartbeat reports stopped backend".into(),
        )),
        _ => Some((
            BackendConnectionState::Error,
            "cohort heartbeat status missing or unsupported".into(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot(status: &str) -> BackendTelemetrySnapshot {
        let mut snapshot = BackendTelemetrySnapshot::disconnected("test fixture");
        snapshot.connection = BackendConnectionState::Connected;
        snapshot.cohort.heartbeat = Some(CohortHeartbeat {
            observed_at: "2026-09-12T00:00:00Z".into(),
            status: Some(status.into()),
        });
        snapshot
    }

    #[test]
    fn running_heartbeat_expires_only_after_the_configured_boundary() {
        let observed: SystemTime = DateTime::parse_from_rfc3339("2026-09-12T00:00:00Z")
            .expect("fixed clock")
            .into();
        let limit = Duration::from_secs(60);
        for age in [Duration::ZERO, limit, limit + Duration::from_millis(1)] {
            let expected = if age <= limit {
                BackendConnectionState::Connected
            } else {
                BackendConnectionState::Stale
            };
            assert_eq!(
                apply(snapshot("running"), observed + age, limit).connection,
                expected
            );
        }
    }

    #[test]
    fn preexisting_source_failures_are_not_hidden_by_a_recent_heartbeat() {
        for state in [
            BackendConnectionState::Error,
            BackendConnectionState::Disconnected,
        ] {
            let mut source = snapshot("running");
            source.connection = state;
            source.status_message = "original source error".into();
            let result = apply(source, SystemTime::now(), Duration::from_secs(60));
            assert_eq!(result.connection, state);
            assert_eq!(result.status_message, "original source error");
        }
    }
}
