# V25 eligible-signal episode BBO markouts

## Problem and acceptance criteria

The prior Screen 6 signal context counted raw eligible annotations. Providers
run at 1m, 5m, 15m, or 30m cadence, so repeated annotations from one persistent
state could be mistaken for independent opportunities.

Acceptance required a read-only path that:

1. obtains cadence from the exact provider identity;
2. starts a new episode only after a gap, side change, or stream boundary;
3. measures the first executable BBO after publication and after each horizon;
4. deducts modeled taker fees and residual slippage;
5. separates overlap-adjusted raw paths from episode-onset paths;
6. reports long, short, pressure, median, and leave-largest evidence; and
7. has no fill, PnL, funding, routing, sizing, or execution authority.

## Implementation

The Python checkpoint audit now publishes cadence-corrected 5m, 15m, 30m,
and 60m executable-BBO markouts under each exact provider-symbol signal row.
Missing legacy cadence reports episode evidence as unavailable. A declared
invalid cadence, an incomplete explicit mapping, inconsistent coverage, or a
non-report-only contract fails validation.

The Rust TUI consumes a strict typed projection. The selected Screen 6
inspector renders compact 30m and 60m episode rows with onset
independent/resolved/eligible counts, net and median bps, leave-largest mean,
long/short coverage, and aligned/opposed pressure. The footer states that the
values are not fills, PnL, funding, or routing evidence.

## Immutable evidence

The authoritative report-only artifact is:

`data/logs/research/bidirectional_cohort/v25_eligible_signal_episode_bbo_markouts_20260809T010900Z.json`

SHA-256:
`ff6e64ea069ca36e91c79175e5231408ba14245e119048ab03e1be635cd04e0a`

Size: `11,248,490` bytes.

| Provider-symbol | Cadence | 60m episode I/R/E | Net bps | Leave-largest bps |
|---|---:|---:|---:|---:|
| Swing/HA GOLD | 15m | 1/1/1 | -22.52 | unavailable |
| Swing/HA SPCX | 15m | 2/2/2 | -6.88 | -30.54 |
| Hulk BTC | 30m | 1/1/1 | -20.67 | unavailable |
| Hulk HYPE | 30m | 1/1/1 | +15.64 | unavailable |
| HT-Breakout ETH | 1m | 2/2/2 | -23.64 | -35.84 |
| HT-Breakout SOL | 1m | 2/3/3 | +15.14 | +6.35 |

All resolved episode samples are long; short-side evidence is zero. All six
providers are negative at 5m and 15m. The corrected SPCX 60m interpretation is
negative; its earlier positive raw repeated-row mean did not survive
provider-cadence episode attribution. SOL is the only two-episode positive 60m
hypothesis, which is insufficient to establish repeatability or justify a live
route change.

## Validation and live isolation

- The focused Python checkpoint/audit suite passed `51` tests.
- Ruff passed for all affected Python production and test files.
- Full `cargo test -p hypervector-tui` passed with zero failures.
- A 160x50 release monitor loaded the current rolling checkpoint and visibly
  rendered `BBO EPISODE ONSETS`, cadence, I/R/E, side, pressure, and report-only
  labels in the provider inspector.
- The checkpoint sidecar alone restarted, from PID `40512` to `48271`.
- The armed live supervisor remained PID `37897`; its run, routes, positions,
  orders, stops, sizing, and strategy logic were not restarted or changed.
- The monitor exited cleanly and left the live backend running.

## Confidence, risks, and falsifiers

Confidence is high for the causal anchor, provider-cadence episode arithmetic,
strict TUI projection, and execution isolation because each has automated and
live-checkpoint validation. Economic confidence is low because every positive
row has at most two independent episode paths and no short sample.

This assessment would change with materially more independent, venue-matched
episode onsets that retain positive after-friction and leave-largest results.
It is falsified technically by cross-run mixing, admitting a pre-publication
book, missing a configured cadence discontinuity, count reconciliation drift,
TUI success-shaped fallback, or any report-only path changing live execution.

