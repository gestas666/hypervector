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

    /// Refresh interval in milliseconds
    #[arg(short, long, default_value_t = 500)]
    pub refresh_ms: u64,

    /// Data root directory
    #[arg(long, default_value = "data")]
    pub data_root: PathBuf,
}
