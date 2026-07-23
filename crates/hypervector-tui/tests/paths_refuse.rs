//! Paper path refuses live; live path refuses paper.

use std::path::{Path, PathBuf};

use hypervector_tui::cli_args::TapeMode;
use hypervector_tui::read::{decisions_path, resolve_tape_path, PathError};

#[test]
fn paper_decisions_path_under_paper() {
    let p = decisions_path(Path::new("/data"), TapeMode::Paper).unwrap();
    assert_eq!(p, PathBuf::from("/data/paper/decisions/decisions.jsonl"));
    assert!(p.to_string_lossy().contains("paper/decisions"));
    assert!(!p.to_string_lossy().contains("live/decisions"));
}

#[test]
fn live_decisions_path_under_live() {
    let p = decisions_path(Path::new("/data"), TapeMode::Live).unwrap();
    assert_eq!(p, PathBuf::from("/data/live/decisions/decisions.jsonl"));
    assert!(p.to_string_lossy().contains("live/decisions"));
    assert!(!p.to_string_lossy().contains("paper/decisions"));
}

#[test]
fn paper_root_cannot_be_live_path() {
    // Constructing a paper path must never equal live path.
    let paper = decisions_path(Path::new("/proj/data"), TapeMode::Paper).unwrap();
    let live = decisions_path(Path::new("/proj/data"), TapeMode::Live).unwrap();
    assert_ne!(paper, live);

    // assert_ledger_segment refuse via wrong expected
    use hypervector_tui::read::paths::assert_ledger_segment;
    let err = assert_ledger_segment(&live, Path::new("/proj/data"), "paper");
    assert!(matches!(err, Err(PathError::CrossLedger { .. })));
    let err = assert_ledger_segment(&paper, Path::new("/proj/data"), "live");
    assert!(matches!(err, Err(PathError::CrossLedger { .. })));
}

#[test]
fn resolve_auto_defaults_paper_when_empty() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    std::fs::create_dir_all(root.join("paper/decisions")).unwrap();
    std::fs::create_dir_all(root.join("live/decisions")).unwrap();
    let (mode, path) = resolve_tape_path(root, TapeMode::Auto).unwrap();
    assert_eq!(mode, TapeMode::Paper);
    assert!(path.ends_with("paper/decisions/decisions.jsonl"));
}

#[test]
fn resolve_auto_prefers_newer_mtime() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    std::fs::create_dir_all(root.join("paper/decisions")).unwrap();
    std::fs::create_dir_all(root.join("live/decisions")).unwrap();
    let paper = root.join("paper/decisions/decisions.jsonl");
    let live = root.join("live/decisions/decisions.jsonl");
    std::fs::write(&paper, "{}\n").unwrap();
    std::thread::sleep(std::time::Duration::from_millis(20));
    std::fs::write(&live, "{}\n").unwrap();
    let (mode, path) = resolve_tape_path(root, TapeMode::Auto).unwrap();
    assert_eq!(mode, TapeMode::Live);
    assert_eq!(path, live);
}
