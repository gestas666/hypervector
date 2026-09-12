//! Read-only file source for authoritative backend telemetry.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use crate::backend_checkpoint_identity::validate_checkpoint_identity;
use crate::backend_cohort::CohortFill;
use crate::backend_cohort_checkpoint::{CohortCheckpointTelemetry, parse_cohort_checkpoint};
use crate::backend_ledger_reader::IncrementalBackendLedger;
use crate::backend_observer::{SourceLongOutcomeTelemetry, parse_source_long_outcome};
use crate::backend_telemetry::{BackendConnectionState, BackendTelemetrySnapshot};
const LIVE_LEDGER_INACTIVITY_LIMIT: Duration = Duration::from_secs(60);
const CHECKPOINT_INACTIVITY_LIMIT: Duration = Duration::from_secs(90);
/// File-backed telemetry source with last-known-good retention.
pub struct BackendTelemetrySource {
    path: PathBuf,
    last_signature: Option<(u64, SystemTime)>,
    backend_reader: IncrementalBackendLedger,
    observer_path: PathBuf,
    observer_signature: Option<(u64, SystemTime)>,
    observer_cached: Option<SourceLongOutcomeTelemetry>,
    checkpoint_path: Option<PathBuf>,
    checkpoint_signature: Option<(u64, SystemTime)>,
    checkpoint_cached: CohortCheckpointTelemetry,
    cached: BackendTelemetrySnapshot,
}

impl BackendTelemetrySource {
    /// Create a read-only source for one backend decisions ledger.
    pub fn new(path: PathBuf) -> Self {
        let observer_path = path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("source_long_outcomes.jsonl");
        Self::with_sidecar_paths(path, observer_path, None)
    }

    /// Create a source with an explicit observe-only outcome sidecar path.
    pub fn with_observer_path(path: PathBuf, observer_path: PathBuf) -> Self {
        Self::with_sidecar_paths(path, observer_path, None)
    }

    /// Create a source with one explicit rolling cohort checkpoint path.
    pub fn with_checkpoint_path(path: PathBuf, checkpoint_path: Option<PathBuf>) -> Self {
        let observer_path = path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("source_long_outcomes.jsonl");
        Self::with_sidecar_paths(path, observer_path, checkpoint_path)
    }

    fn with_sidecar_paths(
        path: PathBuf,
        observer_path: PathBuf,
        checkpoint_path: Option<PathBuf>,
    ) -> Self {
        Self {
            path,
            last_signature: None,
            backend_reader: IncrementalBackendLedger::default(),
            observer_path,
            observer_signature: None,
            observer_cached: None,
            checkpoint_path,
            checkpoint_signature: None,
            checkpoint_cached: CohortCheckpointTelemetry::default(),
            cached: BackendTelemetrySnapshot::disconnected("backend ledger not loaded"),
        }
    }

    /// Refresh when the ledger changes, retaining confirmed state on failure.
    pub fn refresh(&mut self) -> BackendTelemetrySnapshot {
        let snapshot = self.refresh_backend();
        let snapshot = self.attach_observer(snapshot);
        self.attach_checkpoint(snapshot)
    }

    fn refresh_backend(&mut self) -> BackendTelemetrySnapshot {
        let metadata = match fs::metadata(&self.path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return self.missing(),
            Err(error) => return self.failed(format!("backend ledger metadata error: {error}")),
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.last_signature == Some(signature) {
            return apply_live_freshness(self.cached.clone(), modified, SystemTime::now());
        }
        self.load_changed(signature)
    }

    fn attach_observer(
        &mut self,
        mut snapshot: BackendTelemetrySnapshot,
    ) -> BackendTelemetrySnapshot {
        match self.refresh_observer() {
            Ok(outcome) => snapshot.source_long_forward = outcome,
            Err(message) => {
                snapshot.connection = BackendConnectionState::Error;
                snapshot.status_message = message;
            }
        }
        self.cached = snapshot.clone();
        snapshot
    }

    fn refresh_observer(&mut self) -> Result<Option<SourceLongOutcomeTelemetry>, String> {
        let metadata = match fs::metadata(&self.observer_path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(self.observer_cached.clone());
            }
            Err(error) => return Err(format!("source-long sidecar metadata error: {error}")),
        };
        let signature = (
            metadata.len(),
            metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH),
        );
        if self.observer_signature == Some(signature) {
            return Ok(self.observer_cached.clone());
        }
        let content = fs::read_to_string(&self.observer_path)
            .map_err(|error| format!("source-long sidecar read error: {error}"))?;
        let outcome = parse_source_long_outcome(&content).map_err(|error| error.to_string())?;
        self.observer_signature = Some(signature);
        self.observer_cached.clone_from(&outcome);
        Ok(outcome)
    }

    fn attach_checkpoint(
        &mut self,
        mut snapshot: BackendTelemetrySnapshot,
    ) -> BackendTelemetrySnapshot {
        let mut checkpoint = self.refresh_checkpoint();
        if checkpoint.available {
            if let Err(issue) = validate_checkpoint_identity(&snapshot, &checkpoint) {
                checkpoint = CohortCheckpointTelemetry::unavailable(issue);
            } else if !checkpoint.stale
                && let Err(issue) = apply_checkpoint_fill_details(
                    &mut snapshot.cohort.fills,
                    &checkpoint.fill_details,
                )
            {
                checkpoint = CohortCheckpointTelemetry::unavailable(issue);
            }
        }
        snapshot.cohort_checkpoint = checkpoint;
        self.cached = snapshot.clone();
        snapshot
    }

    fn refresh_checkpoint(&mut self) -> CohortCheckpointTelemetry {
        let Some(path) = self.checkpoint_path.clone() else {
            return CohortCheckpointTelemetry::default();
        };
        let metadata = match fs::metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return self.missing_checkpoint(&path);
            }
            Err(error) => {
                return self.failed_checkpoint(format!("checkpoint metadata error: {error}"));
            }
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.checkpoint_signature == Some(signature) {
            return apply_checkpoint_freshness(
                self.checkpoint_cached.clone(),
                modified,
                SystemTime::now(),
            );
        }
        self.load_checkpoint(&path, signature)
    }

    fn load_checkpoint(
        &mut self,
        path: &Path,
        signature: (u64, SystemTime),
    ) -> CohortCheckpointTelemetry {
        let content = match fs::read_to_string(path) {
            Ok(content) => content,
            Err(error) => {
                return self.failed_checkpoint(format!("checkpoint read error: {error}"));
            }
        };
        match parse_cohort_checkpoint(&content) {
            Ok(checkpoint) => {
                self.checkpoint_signature = Some(signature);
                self.checkpoint_cached =
                    apply_checkpoint_freshness(checkpoint, signature.1, SystemTime::now());
                self.checkpoint_cached.clone()
            }
            Err(error) => self.failed_checkpoint(error),
        }
    }

    fn missing_checkpoint(&self, path: &Path) -> CohortCheckpointTelemetry {
        if self.checkpoint_cached.available {
            let mut checkpoint = self.checkpoint_cached.clone();
            checkpoint.stale = true;
            checkpoint.issue = Some("checkpoint disappeared; showing last aggregate".into());
            checkpoint.publication_stale = true;
            checkpoint
        } else {
            CohortCheckpointTelemetry::unavailable(format!(
                "checkpoint not found: {}",
                path.display()
            ))
        }
    }

    fn failed_checkpoint(&self, issue: String) -> CohortCheckpointTelemetry {
        if self.checkpoint_cached.available {
            let mut checkpoint = self.checkpoint_cached.clone();
            checkpoint.stale = true;
            checkpoint.issue = Some(issue);
            checkpoint.publication_stale = true;
            checkpoint
        } else {
            CohortCheckpointTelemetry::unavailable(issue)
        }
    }

    fn load_changed(&mut self, signature: (u64, SystemTime)) -> BackendTelemetrySnapshot {
        match self.backend_reader.load(&self.path, signature.0) {
            Ok(snapshot) => {
                self.last_signature = Some(signature);
                self.cached = apply_live_freshness(snapshot, signature.1, SystemTime::now());
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

fn apply_checkpoint_fill_details(
    fills: &mut [CohortFill],
    details: &[CohortFill],
) -> Result<(), String> {
    let mut corrections = BTreeMap::new();
    for detail in details {
        let identity = (detail.symbol.as_str(), detail.trade_id);
        if corrections.insert(identity, detail).is_some() {
            return Err("checkpoint contains duplicate fill detail identity".into());
        }
    }
    for fill in fills.iter() {
        let Some(detail) = corrections.get(&(fill.symbol.as_str(), fill.trade_id)) else {
            continue;
        };
        if !same_fill_identity(fill, detail) {
            return Err(format!(
                "checkpoint fill detail conflicts with backend trade {}",
                fill.trade_id
            ));
        }
    }
    for fill in fills {
        if let Some(detail) = corrections.get(&(fill.symbol.as_str(), fill.trade_id)) {
            fill.clone_from(detail);
        }
    }
    Ok(())
}

fn same_fill_identity(left: &CohortFill, right: &CohortFill) -> bool {
    left.symbol == right.symbol
        && left.trade_id == right.trade_id
        && left.oid == right.oid
        && left.venue_timestamp_ms == right.venue_timestamp_ms
        && left.price == right.price
        && left.size == right.size
        && left.side == right.side
        && left.direction == right.direction
        && left.fee_usd == right.fee_usd
        && left.closed_pnl_usd == right.closed_pnl_usd
}

fn apply_live_freshness(
    mut snapshot: BackendTelemetrySnapshot,
    modified: SystemTime,
    now: SystemTime,
) -> BackendTelemetrySnapshot {
    if !snapshot.cohort.enabled_symbols.is_empty() {
        return crate::backend_cohort_health::apply(snapshot, now, LIVE_LEDGER_INACTIVITY_LIMIT);
    }
    let armed_live = snapshot.connection == BackendConnectionState::Connected
        && snapshot.execution_mode.as_deref() == Some("live")
        && snapshot.live_armed == Some(true);
    let inactive = now
        .duration_since(modified)
        .is_ok_and(|age| age > LIVE_LEDGER_INACTIVITY_LIMIT);
    if armed_live && inactive {
        snapshot.connection = BackendConnectionState::Stale;
        snapshot.status_message =
            "armed live backend ledger inactive for more than 60s; process health unknown"
                .to_string();
    }
    snapshot
}

fn apply_checkpoint_freshness(
    mut checkpoint: CohortCheckpointTelemetry,
    modified: SystemTime,
    now: SystemTime,
) -> CohortCheckpointTelemetry {
    checkpoint.publication_stale = now
        .duration_since(modified)
        .is_ok_and(|age| age > CHECKPOINT_INACTIVITY_LIMIT);
    checkpoint.stale |= checkpoint.publication_stale;
    if checkpoint.stale && checkpoint.issue.is_none() {
        checkpoint.issue = Some("checkpoint has not refreshed for more than 90s".into());
    }
    checkpoint
}

#[cfg(test)]
#[path = "backend_source_test_fixtures.rs"]
mod test_fixtures;

#[cfg(test)]
#[path = "backend_source_publication_tests.rs"]
mod publication_tests;

#[cfg(test)]
mod tests {
    use std::fs;
    use std::time::Duration;

    use super::test_fixtures::{
        backend_snapshot, cohort_fill, cohort_fill_value, write_live_checkpoint,
    };
    use super::*;

    #[test]
    fn inactive_armed_live_ledger_is_marked_stale() {
        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(120);
        let modified = now - Duration::from_secs(61);
        let mut snapshot = BackendTelemetrySnapshot::disconnected("fixture");
        snapshot.connection = BackendConnectionState::Connected;
        snapshot.execution_mode = Some("live".into());
        snapshot.live_armed = Some(true);
        let observed = apply_live_freshness(snapshot, modified, now);
        assert_eq!(observed.connection, BackendConnectionState::Stale);
        assert!(observed.status_message.contains("inactive"));
    }

    #[test]
    fn recent_or_non_live_ledgers_keep_their_parsed_connection_state() {
        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(120);
        let recent = now - Duration::from_secs(59);
        let mut live = BackendTelemetrySnapshot::disconnected("fixture");
        live.connection = BackendConnectionState::Connected;
        live.execution_mode = Some("live".into());
        live.live_armed = Some(true);
        let mut shadow = live.clone();
        shadow.execution_mode = Some("shadow".into());
        assert_eq!(
            apply_live_freshness(live, recent, now).connection,
            BackendConnectionState::Connected
        );
        assert_eq!(
            apply_live_freshness(shadow, SystemTime::UNIX_EPOCH, now).connection,
            BackendConnectionState::Connected
        );
    }

    #[test]
    fn recent_checkpoint_file_cannot_clear_backend_reported_staleness() {
        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(120);
        let modified = now - Duration::from_secs(1);
        let checkpoint = CohortCheckpointTelemetry {
            configured: true,
            available: true,
            stale: true,
            issue: Some("execution backend heartbeat stale".into()),
            ..CohortCheckpointTelemetry::default()
        };

        let observed = apply_checkpoint_freshness(checkpoint, modified, now);

        assert!(observed.stale);
        assert_eq!(
            observed.issue.as_deref(),
            Some("execution backend heartbeat stale")
        );
    }

    #[test]
    fn configured_checkpoint_sidecar_loads_independently_of_backend() {
        let directory = tempfile::tempdir().expect("tempdir");
        let checkpoint = directory.path().join("latest.json");
        fs::write(
            &checkpoint,
            r#"{
                "schema_version":1,
                "mode":"multi_asset_bidirectional_live_checkpoint",
                "generated_at_utc":"2026-08-02T04:00:00+00:00",
                "status":{"state":"unavailable","technical_issue":"warming up"}
            }"#,
        )
        .expect("checkpoint fixture");
        let mut source = BackendTelemetrySource::with_checkpoint_path(
            directory.path().join("decisions.jsonl"),
            Some(checkpoint),
        );
        let observed = source.refresh_checkpoint();
        assert!(observed.configured);
        assert!(!observed.available);
        assert_eq!(observed.issue.as_deref(), Some("warming up"));
    }

    #[test]
    fn fresh_checkpoint_repairs_matching_backend_fill_details() {
        let directory = tempfile::tempdir().expect("tempdir");
        let checkpoint = directory.path().join("latest.json");
        let corrected = cohort_fill_value(Some(0.0533), Some(1_211), "hulk");
        write_live_checkpoint(&checkpoint, corrected, "run-a");
        let mut source = BackendTelemetrySource::with_checkpoint_path(
            directory.path().join("decisions.jsonl"),
            Some(checkpoint),
        );
        let mut snapshot = backend_snapshot("run-a");
        snapshot.cohort.fills = vec![cohort_fill(None, None, "unattributed")];
        let observed = source.attach_checkpoint(snapshot);
        let fill = &observed.cohort.fills[0];
        assert_eq!(fill.strategy_id, "hulk");
        assert_eq!(fill.slippage_bps, Some(0.0533));
        assert_eq!(fill.acknowledgement_latency_ms, Some(1_211));
        let mut foreign = observed;
        foreign.run_id = Some("run-b".into());
        let rejected = source.attach_checkpoint(foreign);
        assert!(!rejected.cohort_checkpoint.available);
    }

    #[test]
    fn stale_checkpoint_from_another_run_is_rejected() {
        let directory = tempfile::tempdir().expect("tempdir");
        let checkpoint = directory.path().join("latest.json");
        write_live_checkpoint(&checkpoint, cohort_fill_value(None, None, "hulk"), "run-a");
        let modified = SystemTime::now() - CHECKPOINT_INACTIVITY_LIMIT - Duration::from_secs(1);
        fs::File::options()
            .write(true)
            .open(&checkpoint)
            .expect("open checkpoint fixture")
            .set_times(fs::FileTimes::new().set_modified(modified))
            .expect("age checkpoint fixture");
        let mut source = BackendTelemetrySource::with_checkpoint_path(
            directory.path().join("decisions.jsonl"),
            Some(checkpoint),
        );

        let observed = source.attach_checkpoint(backend_snapshot("run-b"));

        assert!(!observed.cohort_checkpoint.available);
        assert!(
            observed
                .cohort_checkpoint
                .issue
                .as_deref()
                .is_some_and(|issue| issue.contains("run identity differs"))
        );
    }
}
