//! Read-only CLI probe — allowlisted subcommands only.
//!
//! Hard allowlist (SRS_HV5_READ_ONLY):
//!   status, paper-check, live-check, paper-report, live-report, regime
//!
//! Never spawn paper-run / live-run / any control plane command.
//!
//! Python resolution (first match wins):
//!   1. explicit `--python` / caller path
//!   2. `HYPERVECTOR_PYTHON` env
//!   3. project `.venv/bin/python` (walk up from data-root and cwd)
//!   4. `uv run python` when `uv` + project `pyproject.toml` exist
//!   5. `python3` / `python` on PATH (last resort)

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

    let launcher = resolve_launcher(python, data_root);
    let data_root_s = data_root.to_string_lossy().into_owned();

    // Actual CLI: `python -m hypervector --data-root X status`
    // Or: `uv run python -m hypervector --data-root X status`
    let mut args: Vec<String> = launcher.prefix.clone();
    args.extend([
        "-m".into(),
        "hypervector".into(),
        "--data-root".into(),
        data_root_s,
        subcommand.into(),
    ]);
    for a in extra_args {
        args.push((*a).into());
    }

    let output = run_with_timeout(&launcher, &args, timeout)?;
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

/// How the probe invokes Python for `python -m hypervector ...`.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Launcher {
    program: PathBuf,
    /// Args inserted before `-m hypervector` (e.g. `uv run python`).
    prefix: Vec<String>,
    /// Optional working directory (needed for `uv run` project discovery).
    current_dir: Option<PathBuf>,
}

fn resolve_launcher(python: Option<&Path>, data_root: &Path) -> Launcher {
    if let Some(p) = python {
        return Launcher {
            program: p.to_path_buf(),
            prefix: Vec::new(),
            current_dir: None,
        };
    }
    if let Ok(p) = std::env::var("HYPERVECTOR_PYTHON") {
        let p = p.trim();
        if !p.is_empty() {
            return Launcher {
                program: PathBuf::from(p),
                prefix: Vec::new(),
                current_dir: None,
            };
        }
    }
    if let Some(venv_py) = find_venv_python(data_root) {
        return Launcher {
            program: venv_py,
            prefix: Vec::new(),
            current_dir: None,
        };
    }
    if let Some(launcher) = find_uv_launcher(data_root) {
        return launcher;
    }
    let program = if path_on_path("python3") {
        PathBuf::from("python3")
    } else {
        PathBuf::from("python")
    };
    Launcher {
        program,
        prefix: Vec::new(),
        current_dir: None,
    }
}

fn find_venv_python(data_root: &Path) -> Option<PathBuf> {
    for root in project_roots(data_root) {
        let candidate = venv_python_path(&root);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn find_uv_launcher(data_root: &Path) -> Option<Launcher> {
    if !path_on_path("uv") {
        return None;
    }
    for root in project_roots(data_root) {
        if root.join("pyproject.toml").is_file() {
            return Some(Launcher {
                program: PathBuf::from("uv"),
                prefix: vec!["run".into(), "python".into()],
                current_dir: Some(root),
            });
        }
    }
    None
}

fn venv_python_path(project_root: &Path) -> PathBuf {
    if cfg!(windows) {
        project_root.join(".venv").join("Scripts").join("python.exe")
    } else {
        project_root.join(".venv").join("bin").join("python")
    }
}

/// Candidate project roots: data-root parent chain, then cwd parent chain.
fn project_roots(data_root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    push_ancestors(&mut out, data_root);
    // If data_root is `.../project/data`, also try its parent first-class.
    if let Ok(cwd) = std::env::current_dir() {
        push_ancestors(&mut out, &cwd);
    }
    out
}

fn push_ancestors(out: &mut Vec<PathBuf>, start: &Path) {
    let mut cur = if start.is_absolute() {
        Some(start.to_path_buf())
    } else {
        std::env::current_dir()
            .ok()
            .map(|cwd| cwd.join(start))
    };
    let mut depth = 0;
    while let Some(path) = cur {
        if !out.iter().any(|p| p == &path) {
            out.push(path.clone());
        }
        if depth >= 8 {
            break;
        }
        cur = path.parent().map(|p| p.to_path_buf());
        depth += 1;
    }
}

fn path_on_path(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn run_with_timeout(
    launcher: &Launcher,
    args: &[String],
    timeout: Duration,
) -> Result<std::process::Output, ProbeError> {
    // Simple blocking spawn; for regime we allow longer timeout from caller.
    // No async runtime in v1 — blocking is fine off the UI thread if we ever
    // split; for now main loop accepts blocking refresh.
    let _ = timeout; // reserved for future non-blocking; still document bound
    let mut cmd = Command::new(&launcher.program);
    cmd.args(args);
    if let Some(dir) = &launcher.current_dir {
        cmd.current_dir(dir);
    }
    let output = cmd.output()?;
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

    #[test]
    fn resolve_launcher_prefers_explicit_python() {
        let p = Path::new("/opt/custom/python");
        let launcher = resolve_launcher(Some(p), Path::new("data"));
        assert_eq!(launcher.program, p);
        assert!(launcher.prefix.is_empty());
        assert!(launcher.current_dir.is_none());
    }

    #[test]
    fn resolve_launcher_prefers_venv_under_project() {
        let tmp = tempfile_project_with_venv();
        let data = tmp.join("data");
        std::fs::create_dir_all(&data).expect("data dir");
        let launcher = resolve_launcher(None, &data);
        let expected = venv_python_path(&tmp);
        assert_eq!(
            launcher.program, expected,
            "expected project .venv python, got {:?}",
            launcher
        );
        assert!(launcher.prefix.is_empty());
        // cleanup
        let _ = std::fs::remove_dir_all(&tmp);
    }

    fn tempfile_project_with_venv() -> PathBuf {
        let base = std::env::temp_dir().join(format!(
            "hv-tui-probe-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        let bin = if cfg!(windows) {
            base.join(".venv").join("Scripts")
        } else {
            base.join(".venv").join("bin")
        };
        std::fs::create_dir_all(&bin).expect("venv bin");
        let py = venv_python_path(&base);
        std::fs::write(&py, b"").expect("touch python");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&py).unwrap().permissions();
            perms.set_mode(0o755);
            std::fs::set_permissions(&py, perms).unwrap();
        }
        base
    }
}
