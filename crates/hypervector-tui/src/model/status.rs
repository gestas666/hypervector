//! Status snapshot from `hypervector status` JSON.
//!
//! Never holds secret string values — only booleans / inventory fields.

use serde::Deserialize;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct StatusSnapshot {
    #[serde(default)]
    pub ok: bool,
    #[serde(default)]
    pub root: String,
    #[serde(default)]
    pub pipeline: PipelineFlags,
    #[serde(default)]
    pub paper: StatusPaper,
    #[serde(default)]
    pub live: StatusLive,
    #[serde(default)]
    pub honesty: HonestyFlags,
    #[serde(default)]
    pub commands: Vec<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct PipelineFlags {
    #[serde(default)]
    pub phase1_research: bool,
    #[serde(default)]
    pub phase2_historical: bool,
    #[serde(default)]
    pub paper_shadow_dry_run: bool,
    #[serde(default)]
    pub live_submit: bool,
    #[serde(default)]
    pub tui_gui: bool,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct StatusPaper {
    #[serde(default)]
    pub default_mode: String,
    #[serde(default)]
    pub no_submit: bool,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct StatusLive {
    #[serde(default)]
    pub submit_wired: bool,
    #[serde(default)]
    pub can_start: bool,
    #[serde(default)]
    pub enabled_default: bool,
    #[serde(default)]
    pub max_notional_usd: f64,
    #[serde(default)]
    pub network: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct HonestyFlags {
    #[serde(default)]
    pub paper_never_constructs_exec_client: bool,
    #[serde(default)]
    pub live_run_fail_closed: bool,
    #[serde(default)]
    pub secret_values_never_printed: bool,
}

impl StatusSnapshot {
    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }

    pub fn from_value(v: &serde_json::Value) -> Result<Self, serde_json::Error> {
        serde_json::from_value(v.clone())
    }

    pub fn network(&self) -> &str {
        if self.live.network.is_empty() {
            "mainnet"
        } else {
            &self.live.network
        }
    }

    pub fn max_notional_usd(&self) -> f64 {
        if self.live.max_notional_usd > 0.0 {
            self.live.max_notional_usd
        } else {
            50.0
        }
    }
}
