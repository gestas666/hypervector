use std::fs;

use chrono::{TimeZone, Utc};
use hypervector_tui::cohort_operator::{
    CohortOperatorAction, CohortOperatorDraft, write_operator_request,
};
use serde_json::Value;
use tempfile::tempdir;

#[test]
fn writes_complete_identity_bound_entry_request_atomically() {
    let temporary = tempdir().expect("tempdir");
    let root = temporary.path();
    fs::create_dir(root.join("pending")).expect("pending");
    let draft = CohortOperatorDraft {
        symbol: "BTC".into(),
        action: CohortOperatorAction::ManualEnter {
            provider: "hulk_expansion_bidirectional_tuned_v2".into(),
            side: "long".into(),
        },
    };

    let path = write_operator_request(
        root,
        "bidirectional-live-1",
        &"a".repeat(64),
        &draft,
        Utc.with_ymd_and_hms(2026, 8, 2, 15, 0, 0)
            .single()
            .expect("time"),
        &"b".repeat(32),
    )
    .expect("request");

    let request: Value =
        serde_json::from_str(&fs::read_to_string(path).expect("content")).expect("request json");
    assert_eq!(request["action"], "manual_enter");
    assert_eq!(request["symbol"], "BTC");
    assert_eq!(request["side"], "long");
    assert_eq!(request["profile_fingerprint"], "a".repeat(64));
    assert!(
        fs::read_dir(root.join("pending"))
            .expect("directory")
            .all(|entry| !entry
                .expect("entry")
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp"))
    );
    assert!(
        !fs::read_to_string(
            root.join("pending")
                .join(format!("{}.json", "b".repeat(32)))
        )
        .expect("request")
        .contains("private_key")
    );
}

#[test]
fn refuses_missing_inbox_and_malformed_identity() {
    let temporary = tempdir().expect("tempdir");
    let draft = CohortOperatorDraft {
        symbol: "BTC".into(),
        action: CohortOperatorAction::ManualClose,
    };
    let now = Utc::now();

    let missing = write_operator_request(
        temporary.path(),
        "run",
        "profile",
        &draft,
        now,
        &"c".repeat(32),
    )
    .expect_err("missing pending directory");
    assert!(missing.to_string().contains("inbox is unavailable"));

    fs::create_dir(temporary.path().join("pending")).expect("pending");
    let malformed =
        write_operator_request(temporary.path(), "run", "profile", &draft, now, "not-an-id")
            .expect_err("invalid id");
    assert!(malformed.to_string().contains("identity is invalid"));
}

#[test]
fn writes_manual_close_for_canonical_hip3_symbol() {
    let temporary = tempdir().expect("tempdir");
    fs::create_dir(temporary.path().join("pending")).expect("pending");
    let draft = CohortOperatorDraft {
        symbol: "xyz:BRENTOIL".into(),
        action: CohortOperatorAction::ManualClose,
    };

    let path = write_operator_request(
        temporary.path(),
        "run",
        "profile",
        &draft,
        Utc.with_ymd_and_hms(2026, 8, 2, 15, 0, 0)
            .single()
            .expect("time"),
        &"a".repeat(32),
    )
    .expect("HIP-3 request");
    let payload: Value =
        serde_json::from_str(&fs::read_to_string(path).expect("content")).expect("request json");

    assert_eq!(payload["symbol"], "xyz:BRENTOIL");
}

#[test]
fn writes_identity_bound_portfolio_transition_drain_request() {
    let temporary = tempdir().expect("tempdir");
    let root = temporary.path();
    fs::create_dir(root.join("pending")).expect("pending");
    let draft = CohortOperatorDraft {
        symbol: "MULTI".into(),
        action: CohortOperatorAction::TransitionDrain,
    };

    let path = write_operator_request(
        root,
        "bidirectional-live-1",
        &"a".repeat(64),
        &draft,
        Utc.with_ymd_and_hms(2026, 8, 5, 13, 0, 0)
            .single()
            .expect("time"),
        &"d".repeat(32),
    )
    .expect("drain request");

    let request: Value =
        serde_json::from_str(&fs::read_to_string(path).expect("content")).expect("request json");
    assert_eq!(request["action"], "transition_drain");
    assert_eq!(request["symbol"], "MULTI");
    assert!(request["provider"].is_null());
    assert!(request["side"].is_null());
    assert!(request["settings"].is_null());
}
