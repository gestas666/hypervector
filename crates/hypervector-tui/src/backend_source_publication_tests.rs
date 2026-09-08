//! Publication freshness must remain independent of reported backend health.

use super::test_fixtures::{cohort_fill_value, write_live_checkpoint};
use super::*;

#[test]
fn publication_timeout_has_an_exact_independent_boundary() {
    let now = SystemTime::UNIX_EPOCH + Duration::from_secs(120);
    for backend_stale in [false, true] {
        for age_seconds in [0, 90, 91] {
            let checkpoint = CohortCheckpointTelemetry {
                stale: backend_stale,
                issue: backend_stale.then(|| "execution backend heartbeat stale".into()),
                ..CohortCheckpointTelemetry::default()
            };
            let modified = now - Duration::from_secs(age_seconds);
            let observed = apply_checkpoint_freshness(checkpoint, modified, now);
            assert_eq!(observed.publication_stale, age_seconds > 90);
            assert_eq!(observed.stale, backend_stale || age_seconds > 90);
            if backend_stale {
                assert_eq!(
                    observed.issue.as_deref(),
                    Some("execution backend heartbeat stale")
                );
            }
        }
    }
}

#[test]
fn missing_and_corrupt_publications_retain_explicitly_historical_values() {
    let directory = tempfile::tempdir().unwrap();
    let checkpoint = directory.path().join("latest.json");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        directory.path().join("decisions.jsonl"),
        Some(checkpoint.clone()),
    );
    write_live_checkpoint(&checkpoint, cohort_fill_value(None, None, "hulk"), "run-a");
    let first = source.refresh_checkpoint();
    assert!(first.available && !first.publication_stale);
    fs::remove_file(&checkpoint).unwrap();
    let missing = source.refresh_checkpoint();
    assert!(missing.available && missing.stale && missing.publication_stale);
    assert_eq!(missing.run_id, first.run_id);
    assert!(missing.issue.as_deref().unwrap().contains("disappeared"));
    fs::write(&checkpoint, "invalid JSON").unwrap();
    let corrupt = source.refresh_checkpoint();
    assert!(corrupt.available && corrupt.stale && corrupt.publication_stale);
    assert_eq!(corrupt.run_id, first.run_id);
    assert!(
        corrupt
            .issue
            .as_deref()
            .unwrap()
            .contains("invalid checkpoint JSON")
    );
    write_live_checkpoint(&checkpoint, cohort_fill_value(None, None, "hulk"), "run-a");
    let recovered = source.refresh_checkpoint();
    assert!(recovered.available && !recovered.stale && !recovered.publication_stale);
    assert_eq!(recovered.run_id, first.run_id);
}

#[test]
fn a_new_publication_clears_a_cached_publication_timeout() {
    let directory = tempfile::tempdir().unwrap();
    let checkpoint = directory.path().join("latest.json");
    write_live_checkpoint(&checkpoint, cohort_fill_value(None, None, "hulk"), "run-a");
    let old = SystemTime::now() - CHECKPOINT_INACTIVITY_LIMIT - Duration::from_secs(1);
    fs::File::options()
        .write(true)
        .open(&checkpoint)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(old))
        .unwrap();
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        directory.path().join("decisions.jsonl"),
        Some(checkpoint.clone()),
    );
    let stale = source.refresh_checkpoint();
    assert!(stale.available && stale.stale && stale.publication_stale);
    write_live_checkpoint(&checkpoint, cohort_fill_value(None, None, "hulk"), "run-a");
    let fresh = source.refresh_checkpoint();
    assert!(fresh.available && !fresh.stale && !fresh.publication_stale);
}
