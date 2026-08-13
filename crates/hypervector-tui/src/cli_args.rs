//! CLI argument parser for Quant TA & Microstructure Regime Detector Cockpit.

use clap::Parser;
use std::path::PathBuf;

#[derive(Debug, Clone, Parser)]
#[command(
    name = "tui-regime-detector",
    about = "Quant TA & Microstructure Regime Detector Cockpit for Hypervector",
    version
)]
pub struct CliArgs {
    /// Trading Symbol (e.g. BTC, ETH)
    #[arg(short, long, default_value = "BTC")]
    pub symbol: String,

    /// Initial Timeframe (1m, 5m, 15m)
    #[arg(short, long, default_value = "5m")]
    pub timeframe: String,

    /// Optional path to historical parquet or JSON file for playback
    #[arg(short, long)]
    pub file: Option<PathBuf>,

    /// Run in real-time live mode
    #[arg(short, long)]
    pub live: bool,

    /// Declare that quitting this process leaves its separately owned backend running
    #[arg(long)]
    pub detached_lifecycle: bool,

    /// Refresh interval in milliseconds
    #[arg(short, long, default_value_t = 500)]
    pub refresh_ms: u64,

    /// Data root directory
    #[arg(long, default_value = "data")]
    pub data_root: PathBuf,

    /// Authoritative backend JSONL ledger (overrides the legacy data-root path)
    #[arg(long)]
    pub backend_ledger: Option<PathBuf>,

    /// Read-only rolling cohort checkpoint produced by the analysis sidecar
    #[arg(long)]
    pub cohort_checkpoint: Option<PathBuf>,

    /// Read-only status checkpoint from the report-only HYPE L2 observer
    #[arg(long)]
    pub hype_l2_observer_status: Option<PathBuf>,

    /// Read-only checkpoint from the execution-incapable HIP-3 roster observer
    #[arg(long)]
    pub hip3_roster_status: Option<PathBuf>,

    /// Read-only point-in-time growth candidate sizing preflight
    #[arg(long)]
    pub growth_preflight: Option<PathBuf>,

    /// Local request inbox consumed only by the already-armed Python backend
    #[arg(long)]
    pub cohort_command_inbox: Option<PathBuf>,

    /// Initial operator screen (1 through 9 for the cohort cockpit)
    #[arg(long, default_value_t = 1, value_parser = parse_initial_tab)]
    pub initial_tab: usize,
}

fn parse_initial_tab(value: &str) -> Result<usize, String> {
    let parsed = value
        .parse::<usize>()
        .map_err(|_| "initial tab must be an integer from 1 through 9".to_string())?;
    if (1..=9).contains(&parsed) {
        Ok(parsed)
    } else {
        Err("initial tab must be from 1 through 9".to_string())
    }
}
