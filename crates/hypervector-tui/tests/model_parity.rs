//! Fixture parity tests for status / gates / tape / regime models.

use std::path::PathBuf;

use hypervector_tui::model::{aggregate_tape, GatesSnapshot, RegimeSnapshot, StatusSnapshot};
use hypervector_tui::read::load_decision_rows;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

#[test]
fn status_fixture_submit_wired_true() {
    let raw = std::fs::read_to_string(fixtures().join("status.json")).unwrap();
    let s = StatusSnapshot::from_json(&raw).expect("parse status");
    assert!(s.ok);
    assert!(s.live.submit_wired, "fixture live.submit_wired must be true");
    assert!(!s.live.can_start);
    assert!((s.live.max_notional_usd - 50.0).abs() < 1e-9);
    assert_eq!(s.network(), "mainnet");
    assert!(s.paper.no_submit);
    assert!(s.honesty.secret_values_never_printed);
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    assert!(v.get("wallet").is_none());
    assert!(v.get("api_key").is_none());
}

#[test]
fn paper_check_gates_bools_only() {
    let raw = std::fs::read_to_string(fixtures().join("paper_check.json")).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let g = GatesSnapshot::from_paper_check(&v);
    assert!(g.paper.no_submit);
    assert!(g.paper.book_feed);
    assert!(g.live.submit_wired);
    assert!(!g.live.enabled);
    assert!(!g.live.can_start);
    assert!(g.layout_ok);
}

#[test]
fn live_check_merge() {
    let paper = std::fs::read_to_string(fixtures().join("paper_check.json")).unwrap();
    let live = std::fs::read_to_string(fixtures().join("live_check.json")).unwrap();
    let mut g = GatesSnapshot::from_paper_check(&serde_json::from_str(&paper).unwrap());
    g.merge_live_check(&serde_json::from_str(&live).unwrap());
    assert_eq!(g.live.start_gate, "refused");
    assert!(!g.live.venue_submit);
    assert!(g.live.submit_wired);
}

#[test]
fn decision_jsonl_last_rows() {
    let path = fixtures().join("decisions_paper.jsonl");
    let rows = load_decision_rows(&path, 10).unwrap();
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0].action.as_deref(), Some("hold"));
    assert_eq!(rows[2].action.as_deref(), Some("sell"));
    assert!(rows.iter().all(|r| r.submitted != Some(true)));
    let agg = aggregate_tape(&rows, 4);
    assert_eq!(agg.decision_count, 3);
    assert_eq!(agg.submitted_count, 0);
}

#[test]
fn regime_fixture_metrics() {
    let raw = std::fs::read_to_string(fixtures().join("regime.json")).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let r = RegimeSnapshot::from_regime_json(&v);
    assert!((r.pct_up - 0.45).abs() < 1e-9);
    assert_eq!(r.n_bars, 1000);
    assert_eq!(r.dominant, "up");
    assert!(r.available);
}
