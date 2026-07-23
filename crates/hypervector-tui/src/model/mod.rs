//! Snapshot types parsed from CLI JSON and decision JSONL.

mod gates;
mod health;
mod regime;
mod snapshot;
pub mod status;
mod tape;

pub use gates::{GatesSnapshot, LiveGates, PaperGates};
pub use health::HealthSnapshot;
pub use regime::RegimeSnapshot;
pub use snapshot::{AppSnapshot, CardId};
pub use status::{HonestyFlags, StatusLive, StatusPaper, StatusSnapshot};
pub use tape::{DecisionRow, TapeAggregate, aggregate_tape};
