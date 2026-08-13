//! Runtime, credential, observer, and evidence configuration rows.

use serde_json::Value;

use super::config_view_format::{
    ConfigMenuRow, effective_arm_state, json_row, masked_credential, metalabel_inference_state,
    number_row, option, row, shadow_reset_command,
};
use crate::backend_telemetry::BackendTelemetrySnapshot;

pub(super) fn observer_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    if backend.observer_policies.is_null() {
        return Vec::new();
    }
    vec![
        json_row(
            "Observer",
            "Long observer authority",
            &backend.observer_policies,
            "execution_authority",
            "observer_policies",
        ),
        json_row(
            "Observer",
            "Long observer side",
            &backend.observer_policies,
            "side",
            "observer_policies",
        ),
        json_row(
            "Observer",
            "Long observer recipes",
            &backend.observer_policies,
            "recipes",
            "observer_policies",
        ),
    ]
}

pub(super) fn apex_mm_runtime_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let mut rows = mode_and_credentials_rows(backend);
    rows.extend(identity_rows(backend));
    rows.extend(apex_mm_detail_rows(backend));
    rows
}

pub(super) fn runtime_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let mut rows = mode_and_credentials_rows(backend);
    rows.extend(identity_rows(backend));
    rows.extend(runtime_detail_rows(backend));
    rows.extend(runtime_lifecycle_rows(backend));
    rows
}

fn mode_and_credentials_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Runtime",
            "Execution mode",
            option(&backend.execution_mode),
            "session_start",
        ),
        row(
            "Runtime",
            "Effective arm state",
            effective_arm_state(backend),
            "backend-confirmed",
        ),
        row(
            "Credentials",
            "Wallet (.env)",
            masked_credential(backend.wallet_configured),
            "presence only",
        ),
        row(
            "Credentials",
            "Signing key (.env)",
            masked_credential(backend.signing_key_configured),
            "presence only",
        ),
    ]
}

fn identity_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Runtime",
            "Strategy",
            option(&backend.strategy_name),
            "session_start",
        ),
        row(
            "Runtime",
            "Profile",
            option(&backend.profile_id),
            "session_start",
        ),
        row(
            "Portfolio",
            "Capital source",
            option(&backend.capital_source),
            "backend-confirmed",
        ),
    ]
}

fn apex_mm_detail_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Runtime",
            "Execution purpose",
            backend
                .runtime
                .get("purpose")
                .and_then(Value::as_str)
                .or(backend.portfolio_purpose.as_deref())
                .unwrap_or("not reported")
                .into(),
            "runtime",
        ),
        row(
            "Runtime",
            "Profitability status",
            backend
                .runtime
                .get("offline_edge_status")
                .and_then(Value::as_str)
                .unwrap_or("not reported")
                .into(),
            "runtime",
        ),
        row(
            "Classification",
            "Regime authority",
            backend
                .regime_policy
                .get("classification")
                .and_then(Value::as_str)
                .unwrap_or("NOT_CLASSIFIED")
                .into(),
            "regime_policy",
        ),
        row(
            "Model",
            "Metalabel mode",
            option(&backend.metalabel_mode),
            "session_start",
        ),
        row(
            "Runtime",
            "Backend ledger",
            option(&backend.backend_ledger_path),
            "session_start",
        ),
    ]
}

fn runtime_detail_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Portfolio",
            "Portfolio purpose",
            option(&backend.portfolio_purpose),
            "backend-confirmed",
        ),
        row(
            "Runtime",
            "Backend ledger",
            option(&backend.backend_ledger_path),
            "session_start",
        ),
        row(
            "Model",
            "Metalabel mode",
            option(&backend.metalabel_mode),
            "session_start",
        ),
        json_row(
            "Model",
            "Metalabel observation",
            &backend.metalabel_policy,
            "observation_type",
            "metalabel_policy",
        ),
        row(
            "Model",
            "Metalabel inference",
            metalabel_inference_state(&backend.metalabel_policy),
            "metalabel_policy",
        ),
    ]
}

fn runtime_lifecycle_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Lifecycle",
            "Shadow reset",
            "explicit CLI only".into(),
            &shadow_reset_command(backend),
        ),
        row(
            "Lifecycle",
            "Active data root",
            super::config_view_format::active_data_root(backend),
            "session_start",
        ),
        number_row(
            "Runtime",
            "Lookback",
            &backend.runtime,
            "lookback_days",
            "runtime",
            "d",
            1.0,
        ),
        json_row(
            "Order book",
            "Archive enabled",
            &backend.orderbook_archive,
            "enabled",
            "orderbook_archive",
        ),
        number_row(
            "Order book",
            "Archive depth",
            &backend.orderbook_archive,
            "depth_levels",
            "orderbook_archive",
            " levels",
            1.0,
        ),
    ]
}

pub(super) fn source_follow_evidence_rows(
    backend: &BackendTelemetrySnapshot,
) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Evidence",
            "Evidence status",
            evidence_status(&backend.runtime),
            "runtime",
        ),
        row(
            "Evidence",
            "Execution economics",
            execution_economics(&backend.runtime),
            "runtime",
        ),
        json_row(
            "Evidence",
            "Active book-gap windows",
            &backend.runtime,
            "active_book_gap_windows",
            "runtime",
        ),
    ]
}

fn evidence_status(runtime: &Value) -> String {
    match runtime.get("evidence_status").and_then(Value::as_str) {
        Some("development_candidate_not_live_proven") => "development / not live proven".into(),
        Some(value) => value.replace('_', " "),
        None => "not reported".into(),
    }
}

fn execution_economics(runtime: &Value) -> String {
    match runtime
        .get("execution_economics_conclusive")
        .and_then(Value::as_bool)
    {
        Some(true) => "conclusive".into(),
        Some(false) => "inconclusive".into(),
        None => "not reported".into(),
    }
}
