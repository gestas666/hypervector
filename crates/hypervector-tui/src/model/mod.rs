//! Snapshot types parsed from CLI JSON and decision JSONL.

mod book;
mod gates;
mod health;
mod readiness;
mod regime;
mod series;
mod snapshot;
pub mod status;
mod tape;

pub use book::BookSnapshot;
pub use gates::{GatesSnapshot, LiveGates, PaperGates};
pub use health::HealthSnapshot;
pub use readiness::{LiveState, ReadinessSnapshot};
pub use regime::RegimeSnapshot;
pub use series::{ActionMix, SeriesSnapshot};
pub use snapshot::{AppSnapshot, CardId};
pub use status::{HonestyFlags, StatusLive, StatusPaper, StatusSnapshot};
pub use tape::{aggregate_tape, DecisionRow, TapeAggregate};
