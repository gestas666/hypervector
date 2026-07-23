//! Regime metrics snapshot — display only; no second detector.

use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct RegimeSnapshot {
    #[serde(default)]
    pub pct_up: f64,
    #[serde(default)]
    pub pct_down: f64,
    #[serde(default)]
    pub pct_range: f64,
    #[serde(default)]
    pub flip_rate: f64,
    #[serde(default)]
    pub mean_duration: f64,
    #[serde(default)]
    pub n_bars: u64,
    /// Dominant label: up | down | range | unknown
    #[serde(default)]
    pub dominant: String,
    /// Seconds since metrics produced (UI-filled).
    #[serde(default)]
    pub age_secs: Option<u64>,
    #[serde(default)]
    pub params_fast: Option<u64>,
    #[serde(default)]
    pub params_slow: Option<u64>,
    #[serde(default)]
    pub provenance: String,
    #[serde(default)]
    pub available: bool,
}

impl RegimeSnapshot {
    /// Parse `hypervector regime` outer JSON (`metrics` nest) or bare metrics object.
    pub fn from_regime_json(v: &Value) -> Self {
        let metrics = v.get("metrics").cloned().unwrap_or_else(|| v.clone());
        let mut snap: RegimeSnapshot =
            serde_json::from_value(metrics.clone()).unwrap_or_default();

        // Dominant from pcts or labels_sample.
        snap.dominant = dominant_label(
            snap.pct_up,
            snap.pct_down,
            snap.pct_range,
            v.get("labels_sample"),
        );

        if let Some(prov) = v.get("data_provenance") {
            snap.provenance = prov.to_string();
        }
        if let Some(params) = v.get("params") {
            snap.params_fast = params
                .get("fast")
                .and_then(|x| x.as_u64())
                .or_else(|| params.get("fast").and_then(|x| x.as_i64()).map(|i| i as u64));
            snap.params_slow = params
                .get("slow")
                .and_then(|x| x.as_u64())
                .or_else(|| params.get("slow").and_then(|x| x.as_i64()).map(|i| i as u64));
        }

        snap.available = snap.n_bars > 0
            || snap.pct_up + snap.pct_down + snap.pct_range > 0.0
            || v.get("metrics").is_some();
        snap
    }

    pub fn empty_hint() -> Self {
        Self {
            dominant: "—".into(),
            available: false,
            ..Default::default()
        }
    }
}

fn dominant_label(up: f64, down: f64, range: f64, sample: Option<&Value>) -> String {
    if let Some(s) = sample {
        if let Some(obj) = s.as_object() {
            let mut best = ("unknown", 0i64);
            for (k, v) in obj {
                let n = v.as_i64().or_else(|| v.as_u64().map(|u| u as i64)).unwrap_or(0);
                if n > best.1 {
                    best = (k.as_str(), n);
                }
            }
            if best.1 > 0 {
                return best.0.to_string();
            }
        }
    }
    let mut pairs = [("up", up), ("down", down), ("range", range)];
    pairs.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    if pairs[0].1 <= 0.0 {
        "unknown".into()
    } else {
        pairs[0].0.into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_regime_metrics_fixture() {
        let v = json!({
            "labels_sample": {"up": 40, "down": 30, "range": 30},
            "metrics": {
                "pct_up": 0.4,
                "pct_down": 0.3,
                "pct_range": 0.3,
                "flip_rate": 0.12,
                "mean_duration": 8.5,
                "n_bars": 100
            },
            "data_provenance": {"source": "fixture"}
        });
        let s = RegimeSnapshot::from_regime_json(&v);
        assert!((s.pct_up - 0.4).abs() < 1e-9);
        assert_eq!(s.n_bars, 100);
        assert_eq!(s.dominant, "up");
        assert!(s.available);
    }
}
