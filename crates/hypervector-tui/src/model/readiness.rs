//! Dry-run readiness — paper/shadow green path vs live refused.

use super::{GatesSnapshot, HealthSnapshot, StatusSnapshot};
use crate::theme::ExecMode;

/// High-level live posture for banner chrome.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LiveState {
    /// Live cannot start (expected dry-run default).
    #[default]
    Refused,
    /// Live checks report can_start (still no arm from TUI).
    Ready,
    /// Live enabled/armed flags true — danger chrome.
    Armed,
}

impl LiveState {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Refused => "LIVE REFUSED",
            Self::Ready => "LIVE READY",
            Self::Armed => "LIVE ARMED",
        }
    }
}

/// At-a-glance readiness for Shadow Ops Floor.
#[derive(Debug, Clone, Default)]
pub struct ReadinessSnapshot {
    /// Paper/shadow dry-run path is instrumented and honest.
    pub dry_run_ready: bool,
    pub paper_mode: String,
    pub live_state: LiveState,
    pub live_reason: String,
    pub network: String,
    pub paper_no_submit: bool,
    pub book_feed: bool,
    pub layout_ok: bool,
}

impl ReadinessSnapshot {
    pub fn from_parts(
        status: &StatusSnapshot,
        gates: &GatesSnapshot,
        health: &HealthSnapshot,
        exec_mode: ExecMode,
    ) -> Self {
        let paper_mode = if !gates.paper.execution_mode.is_empty() {
            gates.paper.execution_mode.clone()
        } else if !status.paper.default_mode.is_empty() {
            status.paper.default_mode.clone()
        } else {
            match exec_mode {
                ExecMode::Live => "live".into(),
                ExecMode::Paper => "paper".into(),
                ExecMode::Shadow => "shadow".into(),
            }
        };

        let paper_no_submit = gates.paper.no_submit || status.paper.no_submit || health.paper_no_submit;
        let book_feed = gates.paper.book_feed;
        let layout_ok = gates.layout_ok;
        let network = {
            let n = if !gates.live.network.is_empty() {
                gates.live.network.as_str()
            } else {
                status.network()
            };
            if n.is_empty() {
                "mainnet".into()
            } else {
                n.to_string()
            }
        };

        let live_can = gates.live.can_start || status.live.can_start;
        let live_armed = gates.live.armed || (gates.live.enabled && live_can);
        let live_state = if live_armed || (gates.live.enabled && gates.live.armed) {
            LiveState::Armed
        } else if live_can {
            LiveState::Ready
        } else {
            LiveState::Refused
        };

        let live_reason = if !gates.live.start_gate_reason.is_empty() {
            gates.live.start_gate_reason.clone()
        } else if !gates.live.start_gate.is_empty() {
            format!("start_gate={}", gates.live.start_gate)
        } else if live_state == LiveState::Refused {
            "live fail-closed".into()
        } else {
            String::new()
        };

        // Dry-run ready: non-live mode, paper honesty, layout present, live not actively placing.
        let non_live = matches!(exec_mode, ExecMode::Shadow | ExecMode::Paper)
            || paper_mode.eq_ignore_ascii_case("shadow")
            || paper_mode.eq_ignore_ascii_case("paper");
        let live_not_submitting = !gates.live.venue_submit;
        let dry_run_ready = non_live
            && paper_no_submit
            && layout_ok
            && live_not_submitting
            && live_state != LiveState::Armed
            && health.live_fail_closed;

        Self {
            dry_run_ready,
            paper_mode,
            live_state,
            live_reason,
            network,
            paper_no_submit,
            book_feed,
            layout_ok,
        }
    }

    pub fn banner_chip(&self, exec_mode: ExecMode) -> &'static str {
        if exec_mode == ExecMode::Live || self.live_state == LiveState::Armed {
            return "LIVE DANGER";
        }
        if self.dry_run_ready {
            "DRY-RUN READY"
        } else if self.live_state == LiveState::Refused {
            "LIVE REFUSED"
        } else {
            "MONITOR"
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{HonestyFlags, LiveGates, PaperGates, StatusLive, StatusPaper};

    #[test]
    fn dry_run_ready_when_shadow_honest() {
        let status = StatusSnapshot {
            ok: true,
            paper: StatusPaper {
                default_mode: "shadow".into(),
                no_submit: true,
            },
            live: StatusLive {
                can_start: false,
                network: "mainnet".into(),
                max_notional_usd: 50.0,
                ..Default::default()
            },
            honesty: HonestyFlags {
                paper_never_constructs_exec_client: true,
                live_run_fail_closed: true,
                secret_values_never_printed: true,
            },
            ..Default::default()
        };
        let gates = GatesSnapshot {
            paper: PaperGates {
                execution_mode: "shadow".into(),
                no_submit: true,
                book_feed: true,
                l2_walk_available: true,
                network: "mainnet".into(),
                ..Default::default()
            },
            live: LiveGates {
                enabled: false,
                armed: false,
                can_start: false,
                start_gate: "refused".into(),
                start_gate_reason: "live.enabled is false".into(),
                network: "mainnet".into(),
                submit_wired: true,
                ..Default::default()
            },
            layout_ok: true,
            ..Default::default()
        };
        let health = HealthSnapshot {
            paper_no_submit: true,
            live_fail_closed: true,
            first_load: false,
            ..Default::default()
        };
        let r = ReadinessSnapshot::from_parts(&status, &gates, &health, ExecMode::Shadow);
        assert!(r.dry_run_ready);
        assert_eq!(r.live_state, LiveState::Refused);
        assert_eq!(r.banner_chip(ExecMode::Shadow), "DRY-RUN READY");
    }
}
