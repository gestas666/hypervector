# Live opportunity capture and decision-time L2 context

## Problem restatement

The live research loop must evaluate more than realized wins and losses. It
must also distinguish moves that were causally visible but not traded, profits
that accepted trades failed to capture, and apparent opportunities created by
overlapping annotations or hindsight. The output remains report-only and must
not mutate the armed live cohort.

Confidence in the measurement contract is high because it is exercised against
immutable ledger snapshots and explicit overlap fixtures. Confidence in any
new trading edge remains low because the live window is short and currently
contains only long-side one-blocker observations.

## Known facts and fixed assumptions

- Exact near misses have a decision-time direction and exactly one blocker.
- Multi-blocker evaluations are not treated as one-condition relaxations.
- Estimated round-trip friction is fixed at `13 bps`; the robust gross-path
  hurdle is fixed at `26 bps`. These are diagnostics, not synthetic fills.
- Independent paths are greedily selected from the earliest decision and may
  not overlap the evaluated horizon.
- L2 context is the latest per-asset `book_observation` received at or before
  the routing-publication timestamp, with a maximum age of 30 seconds.
- The predeclared L2 comparison is directional OPI above zero versus OPI at or
  below zero. No threshold was selected from returns.
- The per-asset ledgers retained roughly 10,000 L2 snapshots per symbol even
  though the consolidated cohort `market_books` events stopped earlier.

## Causal timing correction

The first L2 pass used the completed candle's minute boundary as the decision
boundary. The live router did not publish those evaluations until roughly
18–20 seconds later. A book observed in that gap was knowable when routing ran,
while a hypothetical order could only begin after publication. Tests now make
those two boundaries explicit:

- alignment context: latest book at or before routing publication;
- execution entry: first recorded BBO at or after routing publication;
- fixed exit: first adverse-side BBO at or after the 60-minute deadline;
- one-position constraint: a new candidate cannot overlap the prior simulated
  exit;
- capacity: the full $25 notional must be visible at the top level;
- costs: observed 4.32-bps taker rate per side plus official hourly funding.

This correction supersedes the `15:58:24Z` aligned-versus-opposed table and the
`cohort_orderbook_opportunity_20260804T1600Z_v1.json` interpretation below. The
artifact remains retained as provenance rather than silently rewritten.

## Correction to the original opportunity display

The first display showed the number of independent windows but calculated
cost-clear and robust counts across all overlapping paths. This could count one
sustained move dozens of times. The checkpoint now carries both raw descriptive
capture and `independent_opportunity_capture`; the TUI uses the independent
version and labels it `IND`.

For example, HYPE `5m_not_breakout` at 60 minutes contracted from 461 raw paths
to 9 independent paths in the later L2 snapshot. Seven of the nine reached the
13-bps gross friction hurdle, seven reached the 26-bps robust hurdle, and five
closed above the friction estimate. These are paths, not executable PnL.

## Corrected BTC executable-feasibility result

From `2026-08-04T06:52:12Z` through `15:10:29Z`, the fixed BTC range-onset / exact
`awaiting_hourly_sma_cross` / aligned-OPI contract selected six independent
long entries. All six had timely entry and exit books and enough top-level
capacity. Three were positive and three negative after costs:

| N | W/L | Net total | Mean | PF | Stop-proxy crosses | Short N |
|---:|---:|---:|---:|---:|---:|---:|
| 6 | 3/3 | `+17.90 bps` | `+2.98 bps` | `1.45` | 0 | 0 |

At the fixed $25 canary notional this is only about `$0.045` of hypothetical
net PnL. The useful result is feasibility and frequency—six decisions in 8h18m
without an invented candle fill—not economic validation. One +46.22-bps trade
contributed more than the entire aggregate result, so concentration risk is
high. Removing that observation makes the aggregate negative.

The corrected generic path split is also weaker than the initial claim. Its
globally non-overlapping 60-minute sample contained one aligned path at
`+41.79 bps` after the generic 13-bps hurdle and five opposed paths averaging
`-4.51 bps`. Because that split contains only one aligned observation, it is
not comparative evidence.

## Exit-capture audit

The existing causal HYPE replay already tested 25/15/10, 40/15/20, and
60/15/30-bps activation/floor/giveback policies. Every profit-protection variant
underperformed the fixed-timer control on matched entries; the least-bad
60/15/30 variant still had only one positive development fold out of five. The
latest profitable live HYPE exit does not justify fitting a trailing stop after
the fact.

Lifecycle `HYPE:509645894962` captured 48.33% of its completed-bar MFE and gave
back 110.39 bps before its supported 8-hour exit. Its first five post-exit
minutes reversed by 30.62 bps against the original long, while the completed
15-minute path later ended 23.19 bps in the original direction. This mixed path
supports measuring the timer; it does not identify a better executable exit.

## Risks and failure modes

- Static L2 can be cancelled or spoofed and does not prove traded order flow.
- A latest-prior snapshot does not reveal queue position, fill probability, or
  within-minute event ordering.
- All current executable one-blocker paths are long-side. Pooling them into a
  bidirectional claim would be invalid.
- The BTC executable sample has only six windows and one winner dominates the
  total; the observed PF is unstable.
- The HYPE opposed-OPI result was noticed after inspecting this window and is
  therefore a post-hoc hypothesis, not a selected strategy.

## Recommendation and falsifiers

1. Keep execution unchanged. Do not add a generic trailing stop or a naive
   OPI-alignment gate.
2. Continue the predeclared, report-only BTC range-onset executable replay using
   exact one-blocker paths, OPI sign, both sides, BBO capacity, observed fees,
   official funding, and non-overlapping 60-minute windows.
3. Treat opposed HYPE OPI as an absorption hypothesis only. It requires fresh
   independent windows and preferably executed-trade imbalance before it can
   influence entries.
4. Continue recording accepted-trade MFE capture and post-exit paths beside the
   missed-entry journal.

The BTC hypothesis is weakened if the next independent batch has PF at or below
one after recorded-book execution costs, or if short-side examples contradict
the directional rule. The HYPE
absorption hypothesis is weakened if fresh opposed-OPI windows fail to retain
their advantage or if trade-flow evidence shows the displayed pressure was
real aggressive selling rather than absorption.

## Evidence and validation

- Independent opportunity checkpoint:
  `data/logs/research/cohort_independent_opportunity_capture_20260804T1550Z_v1.json`
  (`bd95cc9b4c114729ed694bf0488a4bc279e04e09d5a0219f75c150cff81ba300`).
- L2 opportunity checkpoint:
  `data/logs/research/cohort_orderbook_opportunity_20260804T1600Z_v1.json`
  (`818713cbee3dd64f71de47bb638005aab560a4a9c9ae5c2ca193a31db96b627b`),
  retained but superseded by the routing-publication correction.
- Corrected executable BTC audit:
  `data/logs/research/cohort_btc_range_one_blocker_execution_20260804T1627Z_v3.json`
  (`7234b1fbd9470460920a07cf7ba65e488dae3ba12ea7983827874bd57b0e75ee`).
- Corrected full live audit:
  `data/logs/research/multi_asset_live_audit_causal_availability_20260804T1630Z_v2.json`
  (`78903366eaf78abda112b8c3f2f374ce378dad338debeab33bdefe4c4d6b0f95`).
  Its `v1` predecessor used the corrected join but retained the old generic
  alignment label; `v2` makes the routing-publication boundary explicit.
- `v1` of the executable audit overlapped a new entry with the preceding
  simulated exit; `v2` repaired that but lacked manifest-bound validation.
  Both remain retained and are superseded by `v3`.
- Tests prove publication-time causality, post-publication BBO entry, adverse
  BBO exit, funding direction, capacity rejection, non-overlap, and separate
  long/short attribution.

Runtime strategies, orders, positions, sizing, and exits were not changed.

Final verification passed 3,266 non-network Python tests with four intentional
deselections, the full Rust/TUI suite, targeted Ruff, Rustfmt, and release
compilation. The read-only checkpoint publisher was reduced to one
launcher-managed process pair and republished both independent capture and L2
coverage. The armed backend was not restarted.
