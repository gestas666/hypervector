use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use crate::backend_telemetry::{BackendTelemetrySnapshot, parse_backend_telemetry_retained};

const REVERSE_SCAN_CHUNK_BYTES: u64 = 1024 * 1024;

#[derive(serde::Deserialize)]
struct LedgerEnvelope {
    event_type: Option<String>,
}

/// Append-aware reader that retains only the bounded backend projection.
#[derive(Default)]
pub(crate) struct IncrementalBackendLedger {
    confirmed_len: Option<u64>,
    retained: Option<String>,
    #[cfg(test)]
    last_read_bytes: u64,
}

impl IncrementalBackendLedger {
    /// Load one confirmed snapshot without rereading an unchanged prefix.
    pub(crate) fn load(
        &mut self,
        path: &Path,
        observed_len: u64,
    ) -> Result<BackendTelemetrySnapshot, String> {
        let (candidate, _bytes_read) = self.read_candidate(path, observed_len)?;
        let (snapshot, retained) =
            parse_backend_telemetry_retained(&candidate).map_err(|error| error.to_string())?;
        self.confirmed_len = Some(observed_len);
        self.retained = Some(retained);
        #[cfg(test)]
        {
            self.last_read_bytes = _bytes_read;
        }
        Ok(snapshot)
    }

    fn read_candidate(&self, path: &Path, observed_len: u64) -> Result<(String, u64), String> {
        match (self.confirmed_len, self.retained.as_deref()) {
            (Some(offset), Some(retained)) if observed_len > offset => {
                let length = observed_len - offset;
                let suffix = read_exact_range(path, offset, length)?;
                Ok((join_jsonl(retained, &suffix), length))
            }
            _ => read_latest_run(path, observed_len),
        }
    }

    #[cfg(test)]
    fn confirmed_len(&self) -> u64 {
        self.confirmed_len.unwrap_or(0)
    }

    #[cfg(test)]
    fn last_read_bytes(&self) -> u64 {
        self.last_read_bytes
    }
}

fn read_latest_run(path: &Path, observed_len: u64) -> Result<(String, u64), String> {
    let mut file =
        File::open(path).map_err(|error| format!("backend ledger open error: {error}"))?;
    let mut chunks: Vec<Vec<u8>> = Vec::new();
    let mut end = observed_len;
    let mut leading_fragment = Vec::new();
    let mut bytes_read = 0_u64;
    while end > 0 {
        let start = end.saturating_sub(REVERSE_SCAN_CHUNK_BYTES);
        let chunk = read_exact_bytes(&mut file, start, end - start)?;
        bytes_read += chunk.len() as u64;
        let mut probe = Vec::with_capacity(chunk.len() + leading_fragment.len());
        probe.extend_from_slice(&chunk);
        probe.extend_from_slice(&leading_fragment);
        if let Some(line_start) = latest_identity_line_offset(&probe, start == 0)
            && line_start < chunk.len()
        {
            let selected_len = observed_len
                .checked_sub(start + line_start as u64)
                .ok_or_else(|| "backend ledger identity offset is invalid".to_string())?;
            let capacity = usize::try_from(selected_len)
                .map_err(|_| "backend ledger current run is too large".to_string())?;
            let mut selected = Vec::with_capacity(capacity);
            selected.extend_from_slice(&chunk[line_start..]);
            for later in chunks.iter().rev() {
                selected.extend_from_slice(later);
            }
            return utf8_content(selected).map(|content| (content, bytes_read));
        }
        leading_fragment = first_line_fragment(&probe);
        chunks.push(chunk);
        end = start;
    }
    let capacity =
        usize::try_from(observed_len).map_err(|_| "backend ledger is too large".to_string())?;
    let mut content = Vec::with_capacity(capacity);
    for chunk in chunks.iter().rev() {
        content.extend_from_slice(chunk);
    }
    utf8_content(content).map(|content| (content, bytes_read))
}

fn latest_identity_line_offset(content: &[u8], allow_first_line: bool) -> Option<usize> {
    let mut line_start = 0;
    let mut latest = None;
    for line_end in content
        .iter()
        .enumerate()
        .filter_map(|(index, byte)| (*byte == b'\n').then_some(index))
        .chain(std::iter::once(content.len()))
    {
        if (allow_first_line || line_start > 0)
            && line_is_configuration_identity(&content[line_start..line_end])
        {
            latest = Some(line_start);
        }
        line_start = line_end.saturating_add(1);
    }
    latest
}

fn line_is_configuration_identity(line: &[u8]) -> bool {
    line.windows("configuration_identity".len())
        .any(|window| window == b"configuration_identity")
        && serde_json::from_slice::<LedgerEnvelope>(line)
            .ok()
            .and_then(|envelope| envelope.event_type)
            .as_deref()
            == Some("configuration_identity")
}

fn first_line_fragment(content: &[u8]) -> Vec<u8> {
    let end = content
        .iter()
        .position(|byte| *byte == b'\n')
        .map_or(content.len(), |index| index + 1);
    content[..end].to_vec()
}

fn read_exact_bytes(file: &mut File, offset: u64, length: u64) -> Result<Vec<u8>, String> {
    file.seek(SeekFrom::Start(offset))
        .map_err(|error| format!("backend ledger seek error: {error}"))?;
    let capacity = usize::try_from(length)
        .map_err(|_| "backend ledger read range is too large".to_string())?;
    let mut content = Vec::with_capacity(capacity);
    file.take(length)
        .read_to_end(&mut content)
        .map_err(|error| format!("backend ledger read error: {error}"))?;
    if content.len() as u64 != length {
        return Err(format!(
            "backend ledger changed during read: expected {length} bytes, read {}",
            content.len()
        ));
    }
    Ok(content)
}

fn utf8_content(content: Vec<u8>) -> Result<String, String> {
    String::from_utf8(content)
        .map_err(|error| format!("backend ledger contains invalid UTF-8: {error}"))
}

fn read_exact_range(path: &Path, offset: u64, length: u64) -> Result<String, String> {
    let mut file =
        File::open(path).map_err(|error| format!("backend ledger open error: {error}"))?;
    read_exact_bytes(&mut file, offset, length).and_then(utf8_content)
}

fn join_jsonl(retained: &str, suffix: &str) -> String {
    if retained.is_empty()
        || suffix.is_empty()
        || retained.ends_with('\n')
        || suffix.starts_with('\n')
    {
        format!("{retained}{suffix}")
    } else {
        format!("{retained}\n{suffix}")
    }
}

#[cfg(test)]
mod tests {
    use std::fs::{self, OpenOptions};
    use std::io::Write;

    use super::*;

    fn session(run_id: &str, equity: f64) -> String {
        serde_json::json!({
            "feed_ts": "session_start",
            "action": "session_start",
            "run_id": run_id,
            "strategy_name": "incremental_reader_fixture",
            "execution_mode": "shadow",
            "init_cash": equity,
            "equity": equity,
            "position_qty": 0.0
        })
        .to_string()
    }

    fn observation(run_id: &str, equity: f64) -> String {
        serde_json::json!({
            "feed_ts": "2026-08-05T15:00:00Z",
            "action": "regime_observation",
            "run_id": run_id,
            "equity": equity,
            "position_qty": 0.0,
            "primary_regime": "TREND_UP"
        })
        .to_string()
    }

    fn configuration_identity(run_id: &str) -> String {
        serde_json::json!({
            "event_type": "configuration_identity",
            "observed_at_utc": "2026-08-05T15:00:00Z",
            "run_id": run_id,
            "payload": {
                "strategy_name": "multi_asset_bidirectional_cohort",
                "enabled_symbols": ["BTC", "ETH", "SOL", "HYPE"]
            }
        })
        .to_string()
    }

    fn heartbeat(run_id: &str) -> String {
        serde_json::json!({
            "event_type": "heartbeat",
            "observed_at_utc": "2026-08-05T15:00:15Z",
            "run_id": run_id,
            "payload": {"state": "running"}
        })
        .to_string()
    }

    #[test]
    fn initial_read_starts_at_latest_configuration_identity() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("decisions.jsonl");
        let old_history = std::iter::repeat_with(|| heartbeat("old-run"))
            .take(12_000)
            .collect::<Vec<_>>()
            .join("\n");
        let old_run = format!("{}\n{old_history}", configuration_identity("old-run"));
        let current_run = format!(
            "{}\n{}",
            configuration_identity("current-run"),
            heartbeat("current-run")
        );
        let ledger = format!("{old_run}\n{current_run}");
        fs::write(&path, &ledger).expect("ledger");
        let reader = IncrementalBackendLedger::default();

        let (candidate, bytes_read) = reader
            .read_candidate(&path, ledger.len() as u64)
            .expect("current run candidate");

        assert_eq!(candidate, current_run);
        assert!(bytes_read < ledger.len() as u64);
    }

    #[test]
    fn identity_free_initial_read_preserves_full_ledger() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("decisions.jsonl");
        let ledger = format!(
            "{}\n{}",
            session("shadow-run", 100.0),
            observation("shadow-run", 101.0)
        );
        fs::write(&path, &ledger).expect("ledger");
        let reader = IncrementalBackendLedger::default();

        let (candidate, bytes_read) = reader
            .read_candidate(&path, ledger.len() as u64)
            .expect("legacy candidate");

        assert_eq!(candidate, ledger);
        assert_eq!(bytes_read, ledger.len() as u64);
    }

    #[test]
    fn append_refresh_reads_only_the_new_suffix() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("decisions.jsonl");
        let initial = session("run-a", 100.0);
        fs::write(&path, &initial).expect("initial ledger");
        let mut reader = IncrementalBackendLedger::default();

        let first = reader
            .load(&path, initial.len() as u64)
            .expect("initial snapshot");
        let suffix = format!("\n{}", observation("run-a", 101.0));
        OpenOptions::new()
            .append(true)
            .open(&path)
            .expect("open append")
            .write_all(suffix.as_bytes())
            .expect("append observation");
        let second = reader
            .load(&path, (initial.len() + suffix.len()) as u64)
            .expect("appended snapshot");

        assert_eq!(first.run_id.as_deref(), Some("run-a"));
        assert_eq!(second.stats.current_equity, 101.0);
        assert_eq!(reader.last_read_bytes(), suffix.len() as u64);
    }

    #[test]
    fn malformed_partial_append_does_not_advance_confirmed_offset() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("decisions.jsonl");
        let initial = session("run-a", 100.0);
        fs::write(&path, &initial).expect("initial ledger");
        let mut reader = IncrementalBackendLedger::default();
        reader
            .load(&path, initial.len() as u64)
            .expect("initial snapshot");
        let partial = "\n{\"feed_ts\":";
        OpenOptions::new()
            .append(true)
            .open(&path)
            .expect("open append")
            .write_all(partial.as_bytes())
            .expect("partial append");

        reader
            .load(&path, (initial.len() + partial.len()) as u64)
            .expect_err("partial JSON must fail");

        assert_eq!(reader.confirmed_len(), initial.len() as u64);
    }

    #[test]
    fn truncation_forces_a_full_reload() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("decisions.jsonl");
        let initial = format!(
            "{}\n{}",
            session("longer-run-identity", 100.0),
            observation("longer-run-identity", 101.0)
        );
        fs::write(&path, &initial).expect("initial ledger");
        let mut reader = IncrementalBackendLedger::default();
        reader
            .load(&path, initial.len() as u64)
            .expect("initial snapshot");
        let replacement = session("new", 77.0);
        fs::write(&path, &replacement).expect("replace ledger");

        let refreshed = reader
            .load(&path, replacement.len() as u64)
            .expect("replacement snapshot");

        assert_eq!(refreshed.run_id.as_deref(), Some("new"));
        assert_eq!(refreshed.stats.current_equity, 77.0);
        assert_eq!(reader.last_read_bytes(), replacement.len() as u64);
    }
}
