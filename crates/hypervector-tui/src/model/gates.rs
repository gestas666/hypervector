//! Paper/live gate snapshots from check JSON (bools only; no secrets).

use serde::Deserialize;

#[derive(Debug, Clone, Default)]
pub struct GatesSnapshot {
    pub paper: PaperGates,
    pub live: LiveGates,
    pub layout_ok: bool,
    pub paper_decisions_path: String,
    pub live_decisions_path: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct PaperGates {
    #[serde(default)]
    pub execution_mode: String,
    #[serde(default)]
    pub no_submit: bool,
    #[serde(default)]
    pub network: String,
    #[serde(default)]
    pub live_feed_loop: bool,
    #[serde(default)]
    pub book_feed: bool,
    #[serde(default)]
    pub l2_walk_available: bool,
    #[serde(default)]
    pub metalabel_enabled: bool,
    /// Presence only — never the secret value.
    #[serde(default)]
    pub secrets_present: bool,
    #[serde(default)]
    pub sandbox_enabled: bool,
    #[serde(default)]
    pub preferred_fill_model: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct LiveGates {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub armed: bool,
    #[serde(default)]
    pub secrets_present: bool,
    #[serde(default)]
    pub can_start: bool,
    #[serde(default)]
    pub submit_wired: bool,
    #[serde(default)]
    pub max_notional_usd: f64,
    #[serde(default)]
    pub network: String,
    #[serde(default)]
    pub start_gate: String,
    #[serde(default)]
    pub start_gate_reason: String,
    #[serde(default)]
    pub venue_submit: bool,
}

impl GatesSnapshot {
    /// Parse paper-check JSON (layout + paper surface + live readiness nest).
    pub fn from_paper_check(v: &serde_json::Value) -> Self {
        let paper_obj = v.get("paper").cloned().unwrap_or(serde_json::json!({}));
        let live_obj = v.get("live").cloned().unwrap_or(serde_json::json!({}));
        let readiness = live_obj
            .get("readiness")
            .cloned()
            .unwrap_or(live_obj.clone());

        let paper: PaperGates = serde_json::from_value(paper_obj).unwrap_or_default();
        let mut live: LiveGates = serde_json::from_value(readiness).unwrap_or_default();
        // Top-level live.submit_wired may exist outside readiness.
        if let Some(sw) = live_obj.get("submit_wired").and_then(|x| x.as_bool()) {
            live.submit_wired = sw;
        }
        if let Some(en) = live_obj.get("enabled").and_then(|x| x.as_bool()) {
            live.enabled = en;
        }

        let dirs = v.get("dirs");
        let layout_ok = dirs
            .and_then(|d| d.get("paper_decisions"))
            .and_then(|p| p.get("exists"))
            .and_then(|e| e.as_bool())
            .unwrap_or(false);

        Self {
            paper,
            live,
            layout_ok,
            paper_decisions_path: v
                .pointer("/paper/decisions")
                .and_then(|x| x.as_str())
                .unwrap_or("")
                .to_string(),
            live_decisions_path: v
                .pointer("/live/decisions")
                .and_then(|x| x.as_str())
                .unwrap_or("")
                .to_string(),
        }
    }

    /// Parse live-check JSON.
    pub fn merge_live_check(&mut self, v: &serde_json::Value) {
        let live_obj = v.get("live").cloned().unwrap_or(v.clone());
        let mut live: LiveGates = serde_json::from_value(live_obj).unwrap_or_default();
        if let Some(sw) = v.get("submit_wired").and_then(|x| x.as_bool()) {
            live.submit_wired = sw;
        }
        if let Some(sg) = v.get("start_gate").and_then(|x| x.as_str()) {
            live.start_gate = sg.to_string();
        }
        if let Some(r) = v.get("start_gate_reason").and_then(|x| x.as_str()) {
            live.start_gate_reason = r.to_string();
        }
        if let Some(vs) = v.get("venue_submit").and_then(|x| x.as_bool()) {
            live.venue_submit = vs;
        }
        self.live = live;
        if let Some(p) = v.get("live_decisions").and_then(|x| x.as_str()) {
            self.live_decisions_path = p.to_string();
        }
    }
}
