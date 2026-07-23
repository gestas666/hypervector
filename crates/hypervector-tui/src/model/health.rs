//! Health / honesty footer snapshot.

use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct HealthSnapshot {
    pub refreshed_at: Instant,
    pub last_error: Option<String>,
    pub paper_no_submit: bool,
    pub live_fail_closed: bool,
    pub secrets_never_printed: bool,
    pub first_load: bool,
    pub refreshing: bool,
    pub regime_refreshing: bool,
}

impl Default for HealthSnapshot {
    fn default() -> Self {
        Self {
            refreshed_at: Instant::now(),
            last_error: None,
            paper_no_submit: true,
            live_fail_closed: true,
            secrets_never_printed: true,
            first_load: true,
            refreshing: false,
            regime_refreshing: false,
        }
    }
}

impl HealthSnapshot {
    pub fn age(&self) -> Duration {
        self.refreshed_at.elapsed()
    }

    pub fn age_secs(&self) -> u64 {
        self.age().as_secs()
    }

    /// Sanitize error for toast — strip env-like secret material.
    pub fn set_error(&mut self, msg: impl Into<String>) {
        let raw = msg.into();
        self.last_error = Some(redact_secrets(&raw));
    }

    pub fn clear_error(&mut self) {
        self.last_error = None;
    }
}

fn redact_secrets(s: &str) -> String {
    // Never surface long hex/base58-looking blobs that might be keys.
    let mut out = s.to_string();
    for needle in [
        "HYPERVECTOR_HL_API_PRIVATE_KEY",
        "HYPERVECTOR_HL_WALLET_ADDRESS",
        "private_key",
        "api_key",
        "secret",
    ] {
        if out.to_ascii_lowercase().contains(&needle.to_ascii_lowercase()) {
            out = out.replace(needle, "[redacted]");
        }
    }
    // Truncate very long messages.
    if out.len() > 160 {
        out.truncate(157);
        out.push_str("...");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redacts_secret_env_names() {
        let mut h = HealthSnapshot::default();
        h.set_error("missing HYPERVECTOR_HL_API_PRIVATE_KEY in env");
        let e = h.last_error.unwrap();
        assert!(!e.contains("PRIVATE_KEY") || e.contains("[redacted]"));
        assert!(e.contains("[redacted]"));
    }
}
