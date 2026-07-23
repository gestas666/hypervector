//! Aggregate app snapshot for floor/focus rendering.

use std::path::PathBuf;

use super::{
    aggregate_tape, DecisionRow, GatesSnapshot, HealthSnapshot, RegimeSnapshot, StatusSnapshot,
    TapeAggregate,
};
use crate::cli_args::TapeMode;
use crate::theme::ExecMode;

/// Focusable cards on the ops floor.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CardId {
    Mode,
    Gates,
    Kpi,
    Regime,
    Tape,
    Health,
}

impl CardId {
    pub const ALL: [CardId; 6] = [
        CardId::Mode,
        CardId::Gates,
        CardId::Kpi,
        CardId::Regime,
        CardId::Tape,
        CardId::Health,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Self::Mode => "MODE",
            Self::Gates => "GATES",
            Self::Kpi => "KPI",
            Self::Regime => "REGIME",
            Self::Tape => "TAPE",
            Self::Health => "HEALTH",
        }
    }

    pub fn next(self) -> Self {
        let all = Self::ALL;
        let i = all.iter().position(|&c| c == self).unwrap_or(0);
        all[(i + 1) % all.len()]
    }

    pub fn prev(self) -> Self {
        let all = Self::ALL;
        let i = all.iter().position(|&c| c == self).unwrap_or(0);
        all[(i + all.len() - 1) % all.len()]
    }
}

#[derive(Debug, Clone)]
pub struct AppSnapshot {
    pub data_root: PathBuf,
    pub tape_mode: TapeMode,
    pub tape_source: TapeMode,
    pub tape_path: Option<PathBuf>,
    pub status: StatusSnapshot,
    pub gates: GatesSnapshot,
    pub decisions: Vec<DecisionRow>,
    pub tape_agg: TapeAggregate,
    pub regime: RegimeSnapshot,
    pub health: HealthSnapshot,
    pub exec_mode: ExecMode,
}

impl AppSnapshot {
    pub fn cold(data_root: PathBuf, tape_mode: TapeMode) -> Self {
        Self {
            data_root,
            tape_mode,
            tape_source: tape_mode,
            tape_path: None,
            status: StatusSnapshot::default(),
            gates: GatesSnapshot::default(),
            decisions: Vec::new(),
            tape_agg: TapeAggregate::default(),
            regime: RegimeSnapshot::empty_hint(),
            health: HealthSnapshot {
                first_load: true,
                ..Default::default()
            },
            exec_mode: ExecMode::Shadow,
        }
    }

    pub fn recompute_mode(&mut self) {
        // Prefer last decision execution_mode, else paper gates, else shadow.
        if let Some(row) = self.decisions.last() {
            if let Some(ref m) = row.execution_mode {
                self.exec_mode = ExecMode::parse(m);
                return;
            }
        }
        if !self.gates.paper.execution_mode.is_empty() {
            self.exec_mode = ExecMode::parse(&self.gates.paper.execution_mode);
            return;
        }
        match self.tape_source {
            TapeMode::Live => self.exec_mode = ExecMode::Live,
            TapeMode::Paper => self.exec_mode = ExecMode::Paper,
            TapeMode::Auto => self.exec_mode = ExecMode::Shadow,
        }
    }

    pub fn recompute_tape_agg(&mut self) {
        self.tape_agg = aggregate_tape(&self.decisions, 24);
    }
}
