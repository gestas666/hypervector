//! Atomic local request writer for backend-owned cohort operator commands.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use chrono::{DateTime, SecondsFormat, Utc};
use serde::Serialize;
use thiserror::Error;

static REQUEST_COUNTER: AtomicU32 = AtomicU32::new(0);

/// Explicit action awaiting a second operator confirmation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CohortOperatorAction {
    ManualEnter { provider: String, side: String },
    ManualClose,
    TransitionDrain,
}

/// Selected symbol and action shown in the confirmation overlay.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CohortOperatorDraft {
    pub symbol: String,
    pub action: CohortOperatorAction,
}

/// Complete editable next-run envelope for one asset.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CohortAssetStageRequest {
    pub symbol: String,
    pub leverage: f64,
    pub margin_fraction: f64,
    pub max_notional_usd: f64,
    pub stop_bps: f64,
    pub maximum_hold_seconds: u64,
}

/// Complete next-run execution scope for one provider.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CohortProviderStageRequest {
    pub strategy_id: String,
    pub execution_symbols: Vec<String>,
}

/// Full staged profile settings submitted for backend validation.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CohortProfileStageRequest {
    pub maximum_positions: usize,
    pub poll_seconds: f64,
    pub assets: Vec<CohortAssetStageRequest>,
    pub providers: Vec<CohortProviderStageRequest>,
}

/// Failure to safely publish a complete command file.
#[derive(Debug, Error)]
pub enum CohortOperatorWriteError {
    #[error("operator command inbox is unavailable: {0}")]
    InboxUnavailable(String),
    #[error("operator command identity is invalid: {0}")]
    InvalidIdentity(String),
    #[error("operator command publication failed: {0}")]
    Publication(String),
}

#[derive(Serialize)]
struct OperatorRequest<'a> {
    schema_version: u8,
    request_id: &'a str,
    run_id: &'a str,
    profile_fingerprint: &'a str,
    created_at_utc: String,
    action: &'static str,
    symbol: &'a str,
    provider: Option<&'a str>,
    side: Option<&'a str>,
    settings: Option<&'a CohortProfileStageRequest>,
}

/// Atomically publish one confirmed request for the matching armed backend.
pub fn write_operator_request(
    inbox_root: &Path,
    run_id: &str,
    profile_fingerprint: &str,
    draft: &CohortOperatorDraft,
    created_at: DateTime<Utc>,
    request_id: &str,
) -> Result<PathBuf, CohortOperatorWriteError> {
    validate_identity(run_id, profile_fingerprint, draft, request_id)?;
    let pending = inbox_root.join("pending");
    if !pending.is_dir() {
        return Err(CohortOperatorWriteError::InboxUnavailable(
            pending.display().to_string(),
        ));
    }
    let (action, provider, side) = request_fields(&draft.action);
    let request = OperatorRequest {
        schema_version: 1,
        request_id,
        run_id,
        profile_fingerprint,
        created_at_utc: created_at.to_rfc3339_opts(SecondsFormat::Millis, true),
        action,
        symbol: &draft.symbol,
        provider,
        side,
        settings: None,
    };
    let bytes = serde_json::to_vec(&request)
        .map_err(|error| CohortOperatorWriteError::Publication(error.to_string()))?;
    publish_bytes(&pending, request_id, &bytes)
}

/// Atomically publish a restart-only profile request for a disarmed backend.
pub fn write_profile_stage_request(
    inbox_root: &Path,
    run_id: &str,
    profile_fingerprint: &str,
    settings: &CohortProfileStageRequest,
    created_at: DateTime<Utc>,
    request_id: &str,
) -> Result<PathBuf, CohortOperatorWriteError> {
    let draft = CohortOperatorDraft {
        symbol: "MULTI".into(),
        action: CohortOperatorAction::ManualClose,
    };
    validate_identity(run_id, profile_fingerprint, &draft, request_id)?;
    if settings.assets.is_empty() || settings.providers.is_empty() {
        return Err(CohortOperatorWriteError::InvalidIdentity(
            "staged profile requires assets and providers".into(),
        ));
    }
    let request = OperatorRequest {
        schema_version: 1,
        request_id,
        run_id,
        profile_fingerprint,
        created_at_utc: created_at.to_rfc3339_opts(SecondsFormat::Millis, true),
        action: "stage_profile",
        symbol: "MULTI",
        provider: None,
        side: None,
        settings: Some(settings),
    };
    let bytes = serde_json::to_vec(&request)
        .map_err(|error| CohortOperatorWriteError::Publication(error.to_string()))?;
    let pending = inbox_root.join("pending");
    if !pending.is_dir() {
        return Err(CohortOperatorWriteError::InboxUnavailable(
            pending.display().to_string(),
        ));
    }
    publish_bytes(&pending, request_id, &bytes)
}

/// Generate a process-local unique lowercase hexadecimal request identity.
pub fn new_request_id() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |value| value.as_nanos() as u64);
    let process = std::process::id();
    let counter = REQUEST_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{nanos:016x}{process:08x}{counter:08x}")
}

fn request_fields(action: &CohortOperatorAction) -> (&'static str, Option<&str>, Option<&str>) {
    match action {
        CohortOperatorAction::ManualEnter { provider, side } => {
            ("manual_enter", Some(provider), Some(side))
        }
        CohortOperatorAction::ManualClose => ("manual_close", None, None),
        CohortOperatorAction::TransitionDrain => ("transition_drain", None, None),
    }
}

fn validate_identity(
    run_id: &str,
    profile: &str,
    draft: &CohortOperatorDraft,
    request_id: &str,
) -> Result<(), CohortOperatorWriteError> {
    let request_valid = request_id.len() == 32
        && request_id
            .chars()
            .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase());
    let symbol_valid = valid_symbol(&draft.symbol);
    if run_id.trim().is_empty() || profile.trim().is_empty() || !request_valid || !symbol_valid {
        return Err(CohortOperatorWriteError::InvalidIdentity(
            "run, profile, request, or symbol identity is malformed".into(),
        ));
    }
    if let CohortOperatorAction::ManualEnter { provider, side } = &draft.action
        && (provider.trim().is_empty() || !matches!(side.as_str(), "long" | "short"))
    {
        return Err(CohortOperatorWriteError::InvalidIdentity(
            "manual entry requires provider and long/short side".into(),
        ));
    }
    if draft.action == CohortOperatorAction::TransitionDrain && draft.symbol != "MULTI" {
        return Err(CohortOperatorWriteError::InvalidIdentity(
            "transition drain requires MULTI portfolio scope".into(),
        ));
    }
    Ok(())
}

fn valid_symbol(symbol: &str) -> bool {
    let venue_symbol = symbol.strip_prefix("xyz:").unwrap_or(symbol);
    !venue_symbol.is_empty()
        && venue_symbol.len() <= 16
        && !venue_symbol.contains(':')
        && venue_symbol
            .chars()
            .all(|value| value.is_ascii_uppercase() || value.is_ascii_digit() || value == '-')
}

fn publish_bytes(
    pending: &Path,
    request_id: &str,
    bytes: &[u8],
) -> Result<PathBuf, CohortOperatorWriteError> {
    let temporary = pending.join(format!(".{request_id}.{}.tmp", std::process::id()));
    let target = pending.join(format!("{request_id}.json"));
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(publication_error)?;
    file.write_all(bytes).map_err(publication_error)?;
    file.write_all(b"\n").map_err(publication_error)?;
    file.sync_all().map_err(publication_error)?;
    fs::hard_link(&temporary, &target).map_err(publication_error)?;
    fs::remove_file(&temporary).map_err(publication_error)?;
    Ok(target)
}

fn publication_error(error: std::io::Error) -> CohortOperatorWriteError {
    CohortOperatorWriteError::Publication(error.to_string())
}
