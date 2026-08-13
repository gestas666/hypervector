//! Strict read projection of backend-audited manual command lifecycle events.

use chrono::{DateTime, FixedOffset};
use serde::Deserialize;
use serde_json::Value;

use crate::backend_telemetry::LedgerRow;

/// One backend acknowledgement for a manually requested operation.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortOperatorEvent {
    #[serde(default)]
    pub observed_at: String,
    pub request_id: String,
    pub status: String,
    pub reason: Option<String>,
    #[serde(rename = "operator_action")]
    pub action: Option<String>,
    pub symbol: Option<String>,
    pub provider: Option<String>,
    pub side: Option<String>,
}

/// Explicit backend-authored state of the portfolio transition drain.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CohortTransitionDrainTelemetry {
    pub status: String,
    pub request_id: Option<String>,
    pub origin_run_id: Option<String>,
    pub run_id: String,
    pub profile_fingerprint: String,
    pub requested_at_utc: Option<String>,
    pub activated_at_utc: Option<String>,
    pub resume_count: usize,
    pub last_resumed_at_utc: Option<String>,
    pub completed_at_utc: Option<String>,
}

pub(crate) fn project_operator_events(
    rows: &[&LedgerRow],
) -> Result<Vec<CohortOperatorEvent>, String> {
    let mut events = Vec::new();
    for row in rows.iter().filter(|row| row.action == "operator_command") {
        let mut event: CohortOperatorEvent = parse_payload(row)?;
        validate_event(&event)?;
        event.observed_at.clone_from(&row.feed_ts);
        events.push(event);
    }
    if events.len() > 30 {
        events.drain(..events.len() - 30);
    }
    Ok(events)
}

fn validate_event(event: &CohortOperatorEvent) -> Result<(), String> {
    let id_valid = event.request_id.len() == 32
        && event
            .request_id
            .chars()
            .all(|character| character.is_ascii_hexdigit() && !character.is_ascii_uppercase());
    let status_valid = matches!(
        event.status.as_str(),
        "received" | "accepted" | "completed" | "rejected" | "drained"
    );
    let action_valid = event.action.as_deref().is_none_or(|value| {
        matches!(
            value,
            "manual_enter" | "manual_close" | "stage_profile" | "transition_drain"
        )
    });
    let side_valid = event
        .side
        .as_deref()
        .is_none_or(|value| matches!(value, "long" | "short"));
    if !id_valid || !status_valid || !action_valid || !side_valid {
        return Err("cohort operator event is structurally invalid".into());
    }
    Ok(())
}

pub(crate) fn validate_transition_drain(
    state: &CohortTransitionDrainTelemetry,
    enclosing_run_id: Option<&str>,
    enclosing_profile_fingerprint: Option<&str>,
) -> Result<(), String> {
    let request_valid = state.request_id.as_deref().is_none_or(lower_hex_32);
    let identity_valid = !state.run_id.trim().is_empty()
        && state.profile_fingerprint.len() == 64
        && state
            .profile_fingerprint
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte));
    if !request_valid || !identity_valid {
        return Err("transition drain identity is invalid".into());
    }
    if enclosing_run_id != Some(state.run_id.as_str())
        || enclosing_profile_fingerprint != Some(state.profile_fingerprint.as_str())
    {
        return Err("transition drain identity differs from cohort snapshot".into());
    }
    let requested = parsed_timestamp(state.requested_at_utc.as_deref())?;
    let activated = parsed_timestamp(state.activated_at_utc.as_deref())?;
    let resumed = parsed_timestamp(state.last_resumed_at_utc.as_deref())?;
    let completed = parsed_timestamp(state.completed_at_utc.as_deref())?;
    let shape_valid = valid_state_shape(state, requested, activated, resumed, completed);
    let chronology_valid = requested
        .zip(activated)
        .is_none_or(|(request, activation)| {
            request <= activation
                && completed.is_none_or(|completion| activation <= completion)
                && valid_resume_shape(state, activation, resumed, completed)
        });
    if !shape_valid || !chronology_valid {
        return Err("transition drain state is inconsistent".into());
    }
    Ok(())
}

fn valid_state_shape(
    state: &CohortTransitionDrainTelemetry,
    requested: Option<DateTime<FixedOffset>>,
    activated: Option<DateTime<FixedOffset>>,
    resumed: Option<DateTime<FixedOffset>>,
    completed: Option<DateTime<FixedOffset>>,
) -> bool {
    match state.status.as_str() {
        "inactive" => {
            state.request_id.is_none()
                && state.origin_run_id.is_none()
                && requested.is_none()
                && activated.is_none()
                && state.resume_count == 0
                && resumed.is_none()
                && completed.is_none()
        }
        "active" | "completed" => {
            state.request_id.is_some()
                && state
                    .origin_run_id
                    .as_deref()
                    .is_some_and(|value| !value.trim().is_empty())
                && requested.is_some()
                && activated.is_some()
                && ((state.status == "completed") == completed.is_some())
        }
        _ => false,
    }
}

fn valid_resume_shape(
    state: &CohortTransitionDrainTelemetry,
    activated: DateTime<FixedOffset>,
    resumed: Option<DateTime<FixedOffset>>,
    completed: Option<DateTime<FixedOffset>>,
) -> bool {
    let Some(origin) = state.origin_run_id.as_deref() else {
        return state.status == "inactive";
    };
    if state.resume_count == 0 {
        return resumed.is_none() && origin == state.run_id;
    }
    resumed.is_some_and(|value| {
        origin != state.run_id
            && value >= activated
            && completed.is_none_or(|completion| value <= completion)
    })
}

fn lower_hex_32(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn parsed_timestamp(value: Option<&str>) -> Result<Option<DateTime<FixedOffset>>, String> {
    value
        .map(|timestamp| {
            DateTime::parse_from_rfc3339(timestamp)
                .map_err(|_| "transition drain timestamp is invalid".to_string())
        })
        .transpose()
}

fn parse_payload<T: for<'de> Deserialize<'de>>(row: &LedgerRow) -> Result<T, String> {
    let values = row.extra.clone().into_iter().collect();
    serde_json::from_value(Value::Object(values))
        .map_err(|error| format!("invalid {} payload: {error}", row.action))
}
