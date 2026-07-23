//! CLI flags for hypervector-tui.

use std::path::PathBuf;

use clap::{Parser, ValueEnum};

/// Which decisions ledger the tape binds to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum, Default)]
pub enum TapeMode {
    /// Prefer the freshest of paper vs live by mtime.
    #[default]
    Auto,
    /// `data_root/paper/decisions/decisions.jsonl`
    Paper,
    /// `data_root/live/decisions/decisions.jsonl`
    Live,
}

/// Args for the read-only ops terminal.
#[derive(Debug, Clone, Parser)]
#[command(
    name = "hypervector-tui",
    about = "Read-only condensed financial ops terminal for hypervector",
    version
)]
pub struct CliArgs {
    /// Project data root (paper/ and live/ ledgers live under this).
    #[arg(long, default_value = "data")]
    pub data_root: PathBuf,

    /// Floor refresh interval for file-backed hot path (milliseconds).
    #[arg(long, default_value_t = 1000)]
    pub refresh_ms: u64,

    /// Decision tape source: paper, live, or auto (mtime).
    #[arg(long, value_enum, default_value_t = TapeMode::Auto)]
    pub tape: TapeMode,

    /// Optional path to `python` (default: `python3` then `python`).
    #[arg(long)]
    pub python: Option<PathBuf>,

    /// Inject fixture status JSON (tests / offline demos).
    #[arg(long, hide = true)]
    pub fixture_status: Option<PathBuf>,

    /// Inject fixture paper-check JSON.
    #[arg(long, hide = true)]
    pub fixture_paper_check: Option<PathBuf>,

    /// Inject fixture live-check JSON.
    #[arg(long, hide = true)]
    pub fixture_live_check: Option<PathBuf>,

    /// Inject fixture regime JSON.
    #[arg(long, hide = true)]
    pub fixture_regime: Option<PathBuf>,
}
