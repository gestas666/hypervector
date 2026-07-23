//! Read-only guard: allowlist only; sources must not spawn control commands.

use std::path::Path;

use hypervector_tui::read::{probe_json, AllowedSubcommand, CLI_ALLOWLIST, CLI_FORBIDDEN};

#[test]
fn allowlist_exact() {
    let expected = [
        "status",
        "paper-check",
        "live-check",
        "paper-report",
        "live-report",
        "regime",
    ];
    assert_eq!(CLI_ALLOWLIST, expected);
    for s in CLI_ALLOWLIST {
        assert!(AllowedSubcommand::parse(s).is_some());
    }
}

#[test]
fn probe_rejects_paper_run_and_live_run() {
    for bad in CLI_FORBIDDEN {
        let err = probe_json(bad, Path::new("data"), None, &[], std::time::Duration::from_secs(1));
        assert!(
            err.is_err(),
            "must reject forbidden subcommand {bad}"
        );
    }
    for bad in ["paper-run", "live-run", "sweep-up", "export"] {
        let err = probe_json(bad, Path::new("data"), None, &[], std::time::Duration::from_secs(1));
        assert!(err.is_err(), "must reject {bad}");
    }
}

#[test]
fn source_tree_has_no_control_spawns() {
    // Static scan of crate sources for spawn of forbidden commands.
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut hits = Vec::new();
    scan_dir(&root, &mut hits);
    // Allow mentions in comments / allowlist constants only if not as spawn args of paper-run.
    // We fail if any .rs file contains `paper-run` or `live-run` outside cli_probe.rs forbidden list.
    for (path, line_no, line) in &hits {
        let p = path.to_string_lossy();
        if p.ends_with("cli_probe.rs") {
            // Forbidden list and docs are OK.
            continue;
        }
        if p.ends_with("effects.rs") || p.ends_with("health.rs") || p.ends_with("mode_banner.rs") {
            // UI copy may mention read-only policy.
            if line.contains("no paper-run") || line.contains("no arm") || line.contains("READ-ONLY")
            {
                continue;
            }
        }
        panic!(
            "forbidden control token in non-allowlist file {p}:{line_no}: {line}"
        );
    }
}

fn scan_dir(dir: &Path, hits: &mut Vec<(std::path::PathBuf, usize, String)>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for ent in rd.flatten() {
        let p = ent.path();
        if p.is_dir() {
            scan_dir(&p, hits);
            continue;
        }
        if p.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(&p) else {
            continue;
        };
        for (i, line) in text.lines().enumerate() {
            if line.contains("paper-run") || line.contains("live-run") {
                hits.push((p.clone(), i + 1, line.to_string()));
            }
        }
    }
}
