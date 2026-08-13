# Repeatable-edge and allocation review — 2026-08-04

## Systems question

Can the current live cohort produce a small positive after-friction expectancy
often enough to matter, and does changing leverage or selective notional improve
that experiment without confusing sizing with signal quality?

## Authoritative live evidence

At the 04:32 EDT rolling checkpoint the armed backend was
`running_consistent`; HYPE was open and protected, BTC/ETH/SOL were flat, and
the compatible-profile ledger contained eight resolved lifecycles.

| Provider-symbol | Closed | W/L | Net after recorded costs | PF |
|---|---:|---:|---:|---:|
| HYPE breakout / HYPE | 4 | 3/1 | +$1.004659 | 5.4867 |
| Hulk expansion / BTC | 1 | 1/0 | +$0.133813 | N/A |
| Source-follow / BTC | 2 | 1/1 | +$0.011029 | 1.0888 |
| Range-onset / ETH | 1 | 0/1 | -$0.174380 | 0.0 |

The HYPE sample contains three longs (`+$0.772171`, PF `4.4485`) and one short
(`+$0.232488`). These are exact venue-lifecycle results, not simulated fills.
They are promising but insufficient to establish repeatability: four outcomes
are concentrated in one short market window and the largest winner contributes
most gross profit. The result remains descriptive and creates no execution
gate.

Observed friction across 18 fills had median acknowledgement latency about
`1.25s` and median fee rate about `4.32 bps`. The live execution-parity audit
reports eight of ten provider-symbol contracts aligned. HYPE breakout differs
from its research model on the new regime-supported maximum-hold extension;
source-follow differs on taker entry and the protective-stop overlay. Therefore
the current live results must not be described as validation of those older
modeled contracts.

## Leverage finding

Keep `5x` for the next controlled comparison. With a fixed `$25` notional cap,
changing leverage does not change dollar PnL; it changes margin consumption and
liquidation distance. The configured `60–80 bps` stops are materially closer
than the approximate `5x` liquidation boundary, and the compatible live sample
contains zero liquidations. Higher leverage is not the measured bottleneck;
lower leverage would consume more margin for the same notional.

Confidence is medium for the leverage recommendation because it follows the
current sizing algebra and venue telemetry, but low for optimality because only
eight trades are resolved. Stop gaps, venue failures, or liquidation-distance
compression would falsify keeping leverage unchanged. Simultaneous margin
utilization becoming binding would justify testing a higher value.

## Selective allocation challenger

The checkpoint now publishes an execution-incapable comparison for only
`hype_breakout_onset_bidirectional_v1|HYPE`:

- current: `$25` notional, `$5` margin, `5x`;
- candidate: `$75` notional, `$15` margin, `5x`;
- current portfolio maximum effective margin: about `5.95%`;
- candidate portfolio maximum effective margin: about `7.93%`;
- Hulk/HYPE and Range-Onset/HYPE remain explicitly pinned at `$25`.

The candidate is not active, has no profit forecast, requires an explicit
future profile change, and carries `performance_gate=false` and
`balance_gate=false`. Account value is an input to the sizing projection at any
positive value; it is not an eligibility threshold.

During the review, a report-only defect was found and corrected: portfolio
reserve telemetry previously used only asset defaults, which could understate a
larger provider override when caps did not bind at lower balances. It now uses
the largest effective provider policy per coin before applying the configured
maximum-position count.

## Validation and falsifiers

- Production-ledger `--once` generation produced the exact current/candidate
  comparison from the active run.
- The release TUI parsed that checkpoint and rendered the candidate in the
  selected HYPE Screen 6 inspector.
- Unit and integration coverage rejects balance/performance authority,
  inconsistent sizing arithmetic, profile changes that fail to pin the other
  HYPE providers, and TUI/risk disagreement.

The early HYPE hypothesis weakens if additional independent trades drive net
expectancy after costs to zero or negative, if profits remain dominated by one
outlier, or if observed opportunity cadence collapses outside this short market
window. It strengthens if both directions continue producing positive
leave-one-out and rolling after-cost expectancy across distinct regimes.
