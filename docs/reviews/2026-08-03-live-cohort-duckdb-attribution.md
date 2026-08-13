# Live cohort DuckDB attribution checkpoint

Date: 2026-08-03 18:01 EDT

## Problem and success criteria

The private live journals were append-only and incrementally imported into
DuckDB, but the analytical schema exposed only raw asset-ledger fills. It did
not retain the provider strategy, expected price, slippage, acknowledgement
latency, markout, controller, exit reason, holding time, or lifecycle net PnL
already present in backend-authored cohort snapshots.

The success criteria were:

1. repeated snapshot history must not duplicate a venue fill;
2. a multi-fill close must remain one queryable close order;
3. the entry provider must own attribution even when one close child is tagged
   with the exit controller;
4. protective stops must remain labeled when the venue fill has no explicit
   `exit_reason`;
5. database status must expose live cohort coverage; and
6. all additions must remain report-only with no execution authority.

## Implemented evidence model

`cohort_live_attributed_fills` expands `recent_fills` from authoritative cohort
snapshots and keeps the latest copy of each `(symbol, trade_id)`. It exposes
provider, controller, expected and actual price, slippage, latency, markout,
fees, funding, holding time, and lifecycle net PnL.

`cohort_live_close_orders` joins each close to its entry provider and groups
multiple venue fills sharing one exit order. A missing explicit exit reason
falls back to the causal operation, such as `protective_stop`.

The status command now reports raw and attributed cohort coverage. The first
production sync after the change reported:

| Metric | Count |
|---|---:|
| Imported cohort events | 123,378 |
| Raw venue fills | 12 |
| Provider-attributed fills | 12 |
| Raw closed fills | 5 |
| Reconstructed close orders | 4 |
| Source ledgers | 5 |
| Recorded run identities | 28 |

Raw-fill and attributed-fill counts are equal at this checkpoint. A future
inequality is an observable coverage failure rather than a silent fallback.

## Current live evidence

At `2026-08-03T22:00:29Z`, the active runtime was
`bidirectional-live-1785781465762`. Its runtime and current configuration
fingerprints both equaled `8dfeee41...19251`. The lifecycle was
`running_consistent`, all three open positions were protected, and there were
zero backend faults.

Compatible-profile history contained four completed trades:

| Provider and side | Trades | W/L | Net PnL | Mean lifecycle fee |
|---|---:|---:|---:|---:|
| HYPE breakout long | 2 | 1/1 | +$0.675571 | $0.021653 |
| HYPE breakout short | 1 | 1/0 | +$0.232488 | $0.021412 |
| BTC source-follow short | 1 | 1/0 | +$0.135163 | $0.021132 |
| **Total** | **4** | **3/1** | **+$1.043222** | — |

Total recorded lifecycle fees were $0.085849 and funding cash flow was
+$0.003251. These are exact journal economics, not a return forecast. Four
trades are insufficient to establish a durable edge.

## New ETH forward event

During validation, `range_onset_bidirectional_v1` opened a protected ETH long:

- completed one-hour SMA 10/30 raw long cross;
- entry reference $1,862.80 and fill $1,862.90;
- 0.537 bps measured slippage and $0.010783 entry fee;
- 0.0134 ETH at 5x, about $24.97 notional and $4.99 margin;
- accepted 60-bps venue stop;
- fixed 48-hour maximum hold.

The entry occurred in canonical 5m `RANGE`, with 1m `TREND_DOWN` and 15m
`TREND_UP`. This is intentional under the frozen range-onset contract, which
admits completed hourly crosses only in 5m `RANGE` or `BREAKOUT`; it is not the
canonical Hypervelocity trend-entry rule. The live event is therefore a direct
forward test of whether the historically SOL-qualified contract transfers to
ETH. The opposing 1m/5m component evidence makes it especially informative,
but does not by itself prove the entry is wrong.

## Risks, limitations, and falsifiers

- Confidence in database attribution is high because duplicated snapshots,
  controller-tagged child fills, multi-fill exits, and missing stop reasons are
  covered by executable tests and matched the production ledger.
- Confidence in strategy profitability remains low because only four closes
  exist and two providers account for all outcomes.
- `cohort_live_close_orders` intentionally groups by exit order. A lifecycle
  closed through multiple distinct exit orders remains multiple close-order
  rows and must not be mislabeled as one atomic order.
- Snapshot attribution depends on the backend retaining each fill in
  `recent_fills`. `attributed_fills < fills` falsifies complete coverage and is
  now visible in `research-db-status`.
- A provider mismatch, wrong entry join, duplicated trade ID, incorrect fee or
  net-PnL total, or any mutation of routing/execution authority falsifies this
  implementation.
- ETH forward PF at or below one across resolved independent signals would
  weaken transfer of the SOL range-onset evidence. One stopped trade would not
  be sufficient by itself.

## Next live checkpoint

1. Preserve the ETH entry and its 5/15/30/60-minute paths, stop behavior,
   funding, and final exit without changing its contract mid-lifecycle.
2. Preserve the current BTC legacy lifecycle until its bound exit; do not
   retroactively rewrite its plan.
3. Compare attributed fills against raw fills after every sync.
4. Update provider-side economics after each close, separating current-run,
   compatible-profile, and independent-window evidence.
5. Do not increase size or infer a profitable portfolio edge from the current
   sample.

The live backend was not restarted or mutated for this work.

## Validation

- Red/green tests proved both new analytical behaviors were absent before the
  implementation.
- 16 focused database and CLI tests passed after the first implementation.
- Two focused stop and multi-fill attribution tests passed after the exit
  reason correction.
- Ruff formatting and lint checks passed on the touched Python sources.
- Production incremental import succeeded with `execution_authority=none` and
  `report_only=true`.

