# Hypervector guides

| Guide | Purpose |
| --- | --- |
| [CLI and headless acceptance](acceptance-visual-and-holistic.md) | What a release must prove: CLI surface, status, install, offline tests, paper/live boundaries. |
| [Transition and rollback](cohort-live-transition-and-rollback.md) | First profile, installed plists, backups, validation, drain, archive, start, acceptance, rollback, interrupted drains and host reboots. |
| [Strategy and regime monitoring](cohort-strategy-regime-monitor.md) | Reading the live checkpoint with `live monitor` and publishing an independent report. |
| [Backend health](cohort-health-telemetry.md) | Heartbeat, lifecycle events and source clocks. |
| [Archived HIP-3 candles](oxa-hip3-candle-history.md) | Fetching and verifying HIP-3 candle evidence from 0xArchive. |
| [Data layout](../infra-data-layout.md) | Where data, ledgers, models, runs and backups live under the data root. |

No strategy is built in. How a research strategy family and a live provider
register is in the README's [Adding a strategy](../../README.md#adding-a-strategy)
section.

The project skills are [hypervector-cli](../../skills/hypervector-cli/SKILL.md)
and [hypervector-regime-detector](../../skills/hypervector-regime-detector/SKILL.md).
The current trading state is in [HANDOFF.md](../../HANDOFF.md). No guide or
code change authorizes a live start; a start needs an explicit operator
instruction.
