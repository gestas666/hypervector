//! Read-only CLI probe — allowlisted subcommands only.
//!
//! Hard allowlist (SRS_HV5_READ_ONLY):
//!   status, paper-check, live-check, paper-report, live-report, regime
//!
//! Never spawn paper-run / live-run / any control plane command.

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use serde_json::Value;
use thiserror::Error;

/// Subcommands the TUI is permitted to spawn.
pub const CLI_ALLOWLIST: &[&str] = &[
    "status",
    "paper-check",
    "live-check",
    "paper-report",
    "live-report",
    "regime",
];

/// Forbidden control-plane commands (must never appear in spawn args).
pub const CLI_FORBIDDEN: &[&str] = &["paper-run", "live-run", "infra-init"];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AllowedSubcommand {
    Status,
    PaperCheck,
    LiveCheck,
    PaperReport,
    LiveReport,
    Regime,
}

impl AllowedSubcommand {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Status => "status",
            Self::PaperCheck => "paper-check",
            Self::LiveCheck => "live-check",
            Self::PaperReport => "paper-report",
            Self::LiveReport => "live-report",
            Self::Regime => "regime",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "status" => Some(Self::Status),
            "paper-check" => Some(Self::PaperCheck),
            "live-check" => Some(Self::LiveCheck),
            "paper-report" => Some(Self::PaperReport),
            "live-report" => Some(Self::LiveReport),
            "regime" => Some(Self::Regime),
            _ => None,
        }
    }
}

#[derive(Debug, Error)]
pub enum ProbeError {
    #[error("subcommand not allowlisted: {0}")]
    NotAllowed(String),
    #[error("cli probe failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("cli exit {code}: {stderr}")]
    Exit { code: i32, stderr: String },
    #[error("invalid json from cli: {0}")]
    Json(#[from] serde_json::Error),
    #[error("probe timed out after {0:?}")]
    Timeout(Duration),
}

/// Run `python -m hypervector <subcommand> ...` → JSON Value.
///
/// `extra_args` must not include forbidden control commands.
pub fn probe_json(
    subcommand: &str,
    data_root: &Path,
    python: Option<&Path>,
    extra_args: &[&str],
    timeout: Duration,
) -> Result<Value, ProbeError> {
    if AllowedSubcommand::parse(subcommand).is_none() {
        return Err(ProbeError::NotAllowed(subcommand.into()));
    }
    for a in extra_args {
        if CLI_FORBIDDEN.contains(a) {
            return Err(ProbeError::NotAllowed((*a).into()));
        }
    }

    let py = resolve_python(python);
    let data_root_s = data_root.to_string_lossy().into_owned();

    let mut args: Vec<String> = vec![
        "-m".into(),
        "hypervector".into(),
        subcommand.into(),
    ];
    // status / checks use global --data-root on the root parser.
    // Always pass --data-root for consistency when the CLI supports it.
    // Some subcommands take it on parent; we pass via env-free explicit flag
    // by prepending after -m hypervector when known.
    // Actual CLI: `python -m hypervector --data-root X status`
    // Rebuild: python -m hypervector --data-root <root> <sub> [extra]
    args = vec![
        "-m".into(),
        "hypervector".into(),
        "--data-root".into(),
        data_root_s,
        subcommand.into(),
    ];
    for a in extra_args {
        args.push((*a).into());
    }

    let output = run_with_timeout(&py, &args, timeout)?;
    if !output.status.success() {
        let code = output.status.code().unwrap_or(-1);
        let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
        return Err(ProbeError::Exit { code, stderr });
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    // Some CLIs may print non-JSON banners; take last JSON object.
    let json_str = extract_json_object(&stdout).unwrap_or(stdout.as_ref());
    Ok(serde_json::from_str(json_str)?)
}

pub fn probe_status(
    data_root: &Path,
    python: Option<&Path>,
) -> Result<Value, ProbeError> {
    probe_json("status", data_root, python, &[], Duration::from_secs(15))
}

fn resolve_python(python: Option<&Path>) -> PathBuf {
    if let Some(p) = python {
        return p.to_path_buf();
    }
    if which("python3") {
        return PathBuf::from("python3");
    }
    PathBuf::from("python")
}

fn which(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn run_with_timeout(
    program: &Path,
    args: &[String],
    timeout: Duration,
) -> Result<std::process::Output, ProbeError> {
    // Simple blocking spawn; for regime we allow longer timeout from caller.
    // No async runtime in v1 — blocking is fine off the UI thread if we ever
    // split; for now main loop accepts blocking refresh.
    let _ = timeout; // reserved for future non-blocking; still document bound
    let output = Command::new(program).args(args).output()?;
    Ok(output)
}

fn extract_json_object(s: &str) -> Option<&str> {
    let start = s.find('{')?;
    let end = s.rfind('}')?;
    if end >= start {
        Some(&s[start..=end])
    } else {
        None
    }
}

/// Load JSON from a fixture file (offline tests / demos).
pub fn load_fixture_json(path: &Path) -> Result<Value, ProbeError> {
    let s = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str(&s)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allowlist_complete() {
        for s in CLI_ALLOWLIST {
            assert!(AllowedSubcommand::parse(s).is_some(), "{s}");
        }
    }

    #[test]
    fn rejects_forbidden() {
        let err = probe_json(
            "paper-run",
            Path::new("data"),
            None,
            &[],
            Duration::from_secs(1),
        );
        assert!(matches!(err, Err(ProbeError::NotAllowed(_))));
    }

    #[test]
    fn rejects_live_run() {
        let err = probe_json(
            "live-run",
            Path::new("data"),
            None,
            &[],
            Duration::from_secs(1),
        );
        assert!(matches!(err, Err(ProbeError::NotAllowed(_))));
    }
}
