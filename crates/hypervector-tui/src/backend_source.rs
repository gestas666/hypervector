//! Read-only file source for authoritative backend telemetry.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::backend_telemetry::{
    BackendConnectionState, BackendTelemetrySnapshot, parse_backend_telemetry,
};

/// File-backed telemetry source with last-known-good retention.
pub struct BackendTelemetrySource {
    path: PathBuf,
    last_signature: Option<(u64, SystemTime)>,
    cached: BackendTelemetrySnapshot,
}

impl BackendTelemetrySource {
    /// Create a read-only source for one backend decisions ledger.
    pub fn new(path: PathBuf) -> Self {
        Self {
            path,
            last_signature: None,
            cached: BackendTelemetrySnapshot::disconnected("backend ledger not loaded"),
        }
    }

    /// Refresh when the ledger changes, retaining confirmed state on failure.
    pub fn refresh(&mut self) -> BackendTelemetrySnapshot {
        let metadata = match fs::metadata(&self.path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return self.missing(),
            Err(error) => return self.failed(format!("backend ledger metadata error: {error}")),
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.last_signature == Some(signature) {
            return self.cached.clone();
        }
        self.load_changed(signature)
    }

    fn load_changed(&mut self, signature: (u64, SystemTime)) -> BackendTelemetrySnapshot {
        let content = match fs::read_to_string(&self.path) {
            Ok(content) => content,
            Err(error) => return self.failed(format!("backend ledger read error: {error}")),
        };
        match parse_backend_telemetry(&content) {
            Ok(snapshot) => {
                self.last_signature = Some(signature);
                self.cached = snapshot;
                self.cached.clone()
            }
            Err(error) => self.failed(error.to_string()),
        }
    }

    fn missing(&self) -> BackendTelemetrySnapshot {
        if self.cached.run_id.is_some() {
            let mut stale = self.cached.clone();
            stale.connection = BackendConnectionState::Stale;
            stale.status_message =
                "backend ledger disappeared; showing last confirmed state".to_string();
            stale
        } else {
            BackendTelemetrySnapshot::disconnected(format!(
                "backend ledger not found: {}",
                self.path.display()
            ))
        }
    }

    fn failed(&self, message: String) -> BackendTelemetrySnapshot {
        if self.cached.run_id.is_some() {
            let mut snapshot = self.cached.clone();
            snapshot.connection = BackendConnectionState::Error;
            snapshot.status_message = message;
            snapshot
        } else {
            BackendTelemetrySnapshot::error(message)
        }
    }

    /// Return the ledger path without mutating backend state.
    pub fn path(&self) -> &Path {
        &self.path
    }
}
