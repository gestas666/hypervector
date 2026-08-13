# v35 post-GOLD close, v39 transition, and v41 growth addendum

## Decision

The next approximately $500 live revision remains v39, but only after the
active v35 portfolio reaches an exact flat and order-free boundary. GOLD,
Range Onset, and both HIP3 Swing providers remain removed. The staged v39
profile retains bidirectional executable authority for every retained route;
it has no observe-only provider.

The $5,000 candidate remains v41. Its sizing arithmetic and recovery clocks
are technically coherent, but its future profitability is not established.
The current file still contains Source Follow and HT-Breakout routes that have
no $5K promotion claim; it is a sizing template, not an approved roster.
The next evidence must come from a correctly reconciled v39 forward window
and then a separately authorized v41 transition.

Confidence is high for the current runtime/accounting reconciliation and the
route-removal decision. Confidence is medium for v39 operational readiness
until a real post-start checkpoint passes. Confidence is low-to-medium for
future portfolio profitability because the historical ledger mixes contracts
and exact v39 has no closed forward sample.

## Authoritative evidence

- Immutable post-GOLD audit:
  `data/logs/research/bidirectional_cohort/v35_live_audit_post_gold_close_20260811T081525Z.json`
- SHA-256:
  `056eb15134a520668d1b2ba71548774d44947ce86b126e4e32f5b419abc9204c`
- Refreshed current v39 preflight:
  `data/runtime/bidirectional_cohort/latest_current_500_v39_preflight.json`
- Refreshed preflight SHA-256:
  `be881e2fb8506aaa6d41d5c2144cf7a5007d1d2949f8882c8b5c6184736e764b`
- Active run: `bidirectional-live-1786402452315`
- Active profile/fingerprint:
  `multi_asset_bidirectional_all_live_canary_v35` /
  `8acc70105f8254dc6a7a3f690cebbaec8b3b81c94547d11b895eb6bbe03a24c4`
- Staged profile/fingerprint:
  `multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39` /
  `8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5`

The refreshed v39 point-in-time preflight observes GOLD flat, reconciles all
eight retained assets, and reports only SOL and SPCX as blockers. It remains a
non-authorizing mid-drain snapshot. Another fresh preflight is required after
every position and owned order is absent.

## Current live state

The v35 backend and checkpoint writer are healthy, their heartbeat is current,
and no asset fault is reported. GOLD is flat and no longer a blocker. The
remaining transition blockers are:

| Asset | Position | Entry | Venue protection | Maximum-hold deadline |
|---|---|---:|---|---|
| SOL | short 0.98 | 75.854 | target 74.147 and reduce-only stop 76.423 | 2026-08-12 01:00 UTC |
| `xyz:SPCX` | long 0.54 | 137.21 | reduce-only stop 136.11 | 2026-08-12 04:45 UTC |

Both venue positions reconcile with their ledger sizes and owned order IDs.
No restart is permitted while either position or order remains. Transition
drain is active and automatic restart is false.

## Reconciled all-time performance

The durable archive and reflection projection both report 50 closed
lifecycles:

- 24 wins / 26 losses / 0 breakeven;
- net +$0.668260;
- profit factor 1.064120;
- fees $1.873894;
- funding +$0.036574;
- maximum closed-sequence drawdown $4.684876;
- median trade -$0.0047725;
- excluding the largest winner: -$1.385964.

The current run has two entry-attributed closed lifecycles, one win and one
loss, for -$0.143080 net. The compatible-profile execution view additionally
includes a -$0.186052 GOLD lifecycle entered under an earlier run and closed
during this run; it must not be relabeled as a current-run entry. Historical
results are descriptive because contracts changed;
they are not a v39 or v41 performance claim.

## Strategy-by-strategy disposition

| Family | Trades | W/L | Net USD | PF | v39 disposition |
|---|---:|---:|---:|---:|---|
| Hulk Expansion | 5 | 4/1 | +1.467771 | 14.338 | Retain BTC/ETH/SOL/HYPE |
| ETH Pullback | 2 | 1/1 | +0.004716 | 1.773 | Retain ETH |
| HIP3 Breakout CMD | 1 | 1/0 | +0.455493 | no loss | Retain SNDK/BRENTOIL |
| HIP3 Swing CMD | 6 | 1/5 | -0.834615 | 0.711 | Remove |
| HIP3 Swing IDX | 3 | 1/2 | +0.305183 | 1.242 | Remove; largest winner dominates |
| HT-Breakout | 27 | 13/14 | -0.451311 | 0.920 | Retain BTC/ETH/SOL only in the ~$500 v39 live-research trial; no $5K promotion claim |
| Hypervelocity Source Follow | 5 | 3/2 | -0.104597 | 0.695 | Retain only in the ~$500 v39 trial; exclude from the $5K successor absent a new causal mechanism |
| Range Onset | 1 | 0/1 | -0.174380 | 0 | Remove |
| HYPE Compression | no compatible live closes | N/A | N/A | N/A | Add HYPE |

The generic HT-Breakout breakdown is BTC -$0.158618, ETH -$0.244318,
HYPE -$0.973612, and SOL +$0.925237. Every route becomes negative when its
largest winner is removed. Retaining BTC/ETH/SOL is therefore an explicit
live-research decision under `SRS_HV1_NO_GATES`, not a statement that those
routes have established edge. Their exact-v39 results must remain separately
visible in the TUI.

### Exact route-level scaling status

No retained v39 provider-symbol-side has an exact v39 close because v39 has
not started. The current and historical ledgers therefore support pruning and
instrumentation decisions, not a v39 profitability claim.

| Route | Current evidence | Approximately $500 v39 | $5,000 status |
|---|---|---|---|
| Hulk BTC | 3 long closes, +$0.233870, PF 3.125, +$0.023768 excluding the largest winner | Retain both sides for forward attribution | Unproven; require exact-contract closes |
| Hulk ETH | no live closes; offline transfer partitions were negative | Retain both sides as an ungated trial | Exclude pending contrary causal evidence |
| Hulk SOL | 1 long close, +$0.681124; current short remains open | Retain both sides | Unproven; isolate long/short evidence |
| Hulk HYPE | 1 long close, +$0.552777; offline transfer was weak | Retain both sides as an ungated trial | Exclude pending contrary causal evidence |
| ETH Pullback | 2 closes, +$0.004716; final historical long slice stronger than short | Retain both sides for contract-separated attribution | Unproven; do not infer bidirectional edge |
| HT-Breakout BTC/ETH/SOL | mixed-contract totals -$0.158618 / -$0.244318 / +$0.925237; each negative excluding its largest winner | Retain as explicitly authorized live research | Exclude pending a new positive mechanism or compatible forward reversal |
| Source Follow BTC | 5 live closes -$0.104597; 782-trade matched-shape replay -$17.823702 | Retain only because the v39 trial is ungated | Exclude from successor roster |
| HYPE Compression | no compatible live closes; development PF 1.115 but only 2/5 positive folds | Add as the highest-value new forward track | Unproven; collect exact closes first |
| HIP3 Breakout BRENTOIL | 1 compatible long close +$0.455493 | Retain both sides | Unproven; one close is insufficient |
| HIP3 Breakout SNDK/SP500/SPCX | no compatible closes | Retain both sides for forward evidence | Exclude pending compatible evidence |

This table is a research disposition, not an implicit performance gate. Under
`SRS_HV1_NO_GATES`, any retained v39 route may trade when its configured
strategy contract fires; the separation controls later sizing decisions and
prevents mixed-contract history from being presented as v39 evidence.

Missed-opportunity telemetry is counterfactual-only: it assumes no fill and
claims no PnL. The strongest retained-v39 hypothesis is three SOL-short
HT-Breakout episodes blocked only by `5m_not_breakout`, averaging +4.43 bps
after the fixed 13-bps hurdle and +2.40 bps after removing the largest. With
only three right-censored episodes and non-point-in-time friction, this is a
candidate diagnostic for the forward journal, not justification to loosen the
entry rule or increase size.

## Trade Oracle and ML4T challenge

The deployed-lifecycle-shape Source Follow replay covers 2025-07-28 through
2026-07-27 and matches the v39 strategy identity, 5x leverage, taker execution,
80-bps stop, 26.67-bps target, 24-hour maximum hold, and the v39 $500 sizing
contract. Fees and slippage are frozen nominal assumptions rather than
point-in-time account-fee and executable-depth observations, so it is not an
exact runtime-friction replay. It also does not match the larger v41 per-asset
sizing identity. Its 782 completed trades produced 571 wins, 211 losses,
-$17.823702 on $500, PF 0.619334, and -3.595168% realized-close maximum
drawdown after $13.082423 in fees. Longs
lost $9.915437 across 365 trades and shorts lost $7.908265 across 417 trades.
This is evidence against the mechanism, not a missing time-exit optimization.
The five live closes do not outweigh that larger matched-contract result.
An equal-trade five-fold chronological diagnostic is also uniformly negative:
fold net results are -$4.681755, -$5.097939, -$3.018677, -$2.781792, and
-$2.243539. Each fold contains 156 or 157 trades and remains negative after
removing its largest winner. This is descriptive reslicing of the frozen
replay, not a new holdout, but it rejects the explanation that one isolated
calendar segment caused the aggregate loss.

The project charter still permits the v39 live trial to run. The evidence
changes the scaling decision: the current v41 file remains a sizing candidate,
not an approved $5K portfolio, because it still includes both Source Follow
and HT-Breakout. A $5K successor must omit those routes, collect compatible
v39 evidence that updates the decision, or carry explicit user-authorized
exceptions.

A genuinely new Source Follow mechanism receives a new immutable identity; a
post-hoc target, stop, session, or hold-time sweep does not qualify.

The proposed EMA challenger requires no new runtime collector. Measured
HT-Breakout evaluations record causal completed-bar directional EMA gaps for
1m and authoritative 5m context, but gaps can be explicitly unavailable after
insufficient history, data gaps, neutral side, or missing sources. The
comparison denominator must report and exclude unavailable feature rows rather
than treating them as zero or gating eligibility. Future rows must also freeze
the EMA periods and semantic source identity before this becomes an immutable
promotion dataset. The report-only comparison is aligned versus opposed entry
PnL under actual fees, funding, and route-specific slippage, with median
return, fold stability, and largest-winner removal. It must not gate a lone
intent or alter live size.

HYPE Compression already tested the rounded 5m/prior-1m BBWP neighborhood
40/40, 50/40, and 50/50 against the unchanged control. The selected 50/40 arm
was positive in aggregate but had only two of five positive development folds;
the later four-trade confirmation became negative after removing its largest
winner. None of the three compression arms produced a positive median
development fold: their median fold returns were -216.16, -202.36, and
-453.39 bps respectively. PMARP would be a new mechanism rather than a
robustness check and is not added. The existing rounded arms remain frozen for
exact forward comparison.

Trade Oracle supplied useful principles about medians, winner concentration,
and keeping moving averages contextual. Its suggested fixed sample and PF
thresholds are not adopted as automatic gates: they were generic priors rather
than project-derived decision boundaries. ML4T discipline instead freezes the
decision-time feature contract, uses chronological evaluation, fits nothing on
the forward window, applies actual and stress costs separately, and treats
regime as a context lens rather than a standalone timing signal.

Trade Oracle also suggested a five-minute horizontal-range wick sweep and
close-inside reclaim. That family is not a new experiment here. The frozen
184-day project study already evaluated 15,321 non-overlapping BTC/SOL
lifecycles on both sides. Continuation produced 6,396 trades with -13.37 bps
mean after cost and PF 0.529; reversal/reclaim produced 8,925 trades with
-12.00 bps mean and PF 0.428. Both remained negative before fees, across every
fold, asset/side cell, and regime slice. Repeating the same mechanism or a
nearby parameter sweep is therefore rejected as duplicated research. It is
reopened only by a preregistered materially different causal mechanism, not by
renaming or lightly retuning the same range-reclaim rule.

Confidence is high that the existing Source Follow mechanism should not be
promoted automatically because its v39-shaped replay is large and negative on
both sides. The same mechanism remains negative even with zero modeled fees
and slippage, although only narrowly: 785 trades, -$0.872033, PF 0.977724.
This is strong exclusion evidence, but it is neither exact runtime friction nor
an exact v41 $5K replay. A point-in-time fee/depth replay at v41 size would
update the scaling conclusion if nonlinear slippage or venue constraints
materially changed the result. Confidence is
low-to-medium that EMA context or HYPE Compression has forward edge because
compatible live samples are still small. These conclusions are falsified by a
new immutable causal mechanism with positive chronological after-cost evidence
that remains positive after its largest winner is removed; ordinary v39 trial
losses or wins remain reported results and do not automatically stop execution.

## GOLD conclusion

GOLD HIP3 Swing finished 0W/3L, -$1.197088, PF 0. The final GOLD long closed
at 4359.8 after a 4362.0 entry for -$0.186052 net, including $0.128858 fees
and -$0.019574 funding. It reached about +174 bps favorable excursion and
gave back about 179 bps before closing.

The small sample prevents a permanent claim about GOLD as a market. It is
sufficient to remove this specific GOLD/Swing route now: it has no positive
live lifecycle evidence, poor entries, and unvalidated exit capture. The
source and ledgers remain preserved for a separately identified challenger.

## Regime telemetry and routing

The active v35 histories contain unavailable canonical regime context, so
they cannot prove regime-classification accuracy. The missing HIP3 pressure
values were traced to the old post-close receipt contract: some decisions were
routed before a new post-close book arrived. That produced a safe no-trade but
incomplete telemetry.

The staged implementation now:

1. accepts multiple ordered same-symbol recovery decisions;
2. rejects duplicate or unordered recovery identities;
3. binds each intent to the latest canonical row at or before its own
   decision, preventing future-row rewrites;
4. treats `UNKNOWN` as no routing or hold-extension support;
5. uses regime only to rank simultaneous conflicts, not to block a lone
   otherwise-valid intent; and
6. requires fresh causal complete BTC/ETH/SOL/HYPE rows in v39 post-start
   acceptance; and
7. measures freshness from both persistence time and the underlying market
   decision time, so a newly written old decision cannot pass acceptance.

This is a causal correctness improvement, not an accuracy result. Accuracy is
accepted only after the v39 runtime produces real canonical rows whose
component directions, freshness, and timestamps reconcile against source
bars. Warm-up nulls, stale rows, or UNKNOWN states fail the post-start check.

## TUI acceptance

The TUI monitor is read-only and must show active v35 truth alongside staged
v39 truth. At 160x50, the real checkpoint QA requires:

- all-time 50 closed and current run 2 closed;
- all nine active v35 asset identities;
- SOL and `xyz:SPCX` open with venue stops/exit plans;
- exact HIP3 symbols without aliases or truncation;
- v39 as 8 assets, 14 provider-symbol routes, and 28 long/short scopes;
- explicit blockers SOL and `xyz:SPCX`;
- unavailable provider-only regime fields labeled rather than blank; and
- no stale command authority or automatic-restart claim.

Two display defects were reproduced and fixed test-first: Screen 2 exact HIP3
symbols were truncated, and Screen 9 omitted staged asset/side totals. The
transition fixtures also prove 24 active routes to 14 staged routes, 11
removals, one addition, no observe-only provider, and honest compact-screen
overflow.

A third display defect was reproduced and fixed: Screen 8's state matrix
recognized the canonical v39 telemetry identity, but its range, strength, and
focus panels recognized only the retired legacy provider and could display the
same row as provider-only. All Screen 8 diagnostic selectors now use the same
canonical identity helper without changing provider or execution authority.

## v41 $5,000 sizing contract

v41 contains eight executable assets and ten capacity slots. Because the
portfolio allows one position per asset, its present simultaneous maximum is
eight positions, not ten. Two slots are intentionally unused until additional
assets have venue-compatible evidence.

The exact v41 configuration uses:

- isolated 5x leverage;
- risk-normalized margin fractions summing to 24%;
- $1,200 total initial margin at $5,000 equity;
- $6,000 gross notional, or 1.2x account exposure;
- source-bound modeled simultaneous stop-wave p99 of $58.02, or 1.1605% of
  account equity.

The p99 number is a deterministic modeled scenario, not a probability, hard
loss ceiling, or profitability estimate. Gaps, latency, and correlated moves
can exceed it.

All 14 provider-symbol routes and all 28 side scopes currently have zero exact
v39/v41 closed lifecycles. The eight-asset return panel also has zero common
timestamps, so covariance, co-trigger probability, and portfolio-level
diversification benefit are unmeasured. The modeled p99 contributions are
balanced across assets, but equalized standalone losses do not establish
independence.

The present v41 file is therefore retained as a sizing template only. The
evidence-ranked successor research shortlist is:

- prioritize HYPE Compression under its exact v39 contract;
- conditionally retain Hulk BTC, Hulk SOL, HT-Breakout BTC, and HIP3 Breakout
  SP500 long enough to resolve contradictory or approximate evidence;
- exclude Hulk ETH/HYPE, Source Follow BTC, HT-Breakout ETH/SOL, ETH Pullback,
  and HIP3 Breakout SPCX/SNDK/BRENTOIL from a $5,000 successor unless a new
  causal mechanism identity or materially contrary exact forward evidence is
  produced.

This shortlist is not applied to the authorized approximately $500 v39 trial
and is not a runtime gate. Its purpose is to prevent negative mixed-contract
history from being silently scaled five- to ten-fold merely because the sizing
arithmetic is internally valid.

A recovery defect was corrected: a same-profile protected position restored
without a persisted execution plan could previously inherit a 48-hour asset
fallback even though its executable v41 providers terminate within 24 hours.
Planless recovery is now bounded by the longest executable provider terminal
for that symbol. Persisted plans and explicitly configured 48-hour providers
remain unchanged.

## Unused-capacity candidates

The ten-position account setting is capacity, not a requirement to populate
weak routes. The current eight-asset portfolio therefore retains two unused
slots while CL and MU collect evidence under separate identities.

The immutable CL development-only diagnostic is
`data/logs/research/xyz_cl_development_only_diagnostic_20260811_v1.json`,
SHA-256 `fca63ef8dd933037159a7171ec3f58d0a349d10983f6afc5d6762f036e223327`.
It selected the 15-minute bidirectional breakout-pressure family with EMA
21/55, a four-bar breakout lookback, 0.10 absolute imbalance threshold, and a
40-bps structural stop under the 80-bps risk ceiling. Development produced 81
trades, +$5.251185 nominal at PF 1.2427 and +$3.313589 under stress at
PF 1.1427. Longs were positive after largest-winner removal; shorts were
negative. All three chronological folds were positive in aggregate, but every
fold became negative after removing its largest winner. More importantly,
59/81 selected lifecycles crossed unresolved exact mark paths. Validation and
holdout were not evaluated. CL remains report-only and is not added to a live
roster. Resolved path evidence, then untouched validation and holdout, would
update that disposition.

The MU pre-close pressure observer now has an isolated unsigned public-data
runner, exact durable cursor, append-only journal, and no signer, intent, order,
router, or configuration registration. Two bounded real polls proved bootstrap
and restart without retroactive replay. It remains data collection only because
row-for-row parity between live 15-minute `candleSnapshot` OHLC and the archive
public-trade OHLC contract is unverified. MU is not added to a live roster until
that technical identity is resolved and prospective evidence exists.

## Transition sequence

1. Continue v35 drain while SOL and SPCX remain venue-protected.
2. Require venue and every v35 ledger to be flat with no owned orders.
3. Generate a fresh v39 mainnet preflight and reconcile exact assets, sizes,
   fees, leverage, orders, profile fingerprint, and 14-route roster.
4. Stop v35 normally and preserve its ledgers plus a new prestart backup.
5. Start v39 only with both explicit live-risk flags already authorized by
   the user.
6. After all eight ledgers advance, run the v39 post-start verifier and check
   stops, fees, funding, regime telemetry, route accounting, and the TUI.
7. Start `scripts/v39_forward_evidence_monitor.py` only after that verifier
   passes. It pins the exact v39 fingerprint, reports all 14 routes, separates
   28 configured sides from sides actually evaluated, rejects stale or
   contradictory inputs, and keeps current-run closes separate from mixed
   historical results.
8. Keep v39 forward lifecycles contract-separated from historical results.
9. Reprice v41 from the actual $5,000 account immediately before its later
   separately authorized launch.

## Falsifiers and update conditions

This recommendation changes if any of the following occurs:

- the live heartbeat becomes stale or runtime/checkpoint identities diverge;
- SOL or SPCX loses full reduce-only stop coverage;
- archive and reflection closed counts diverge from 50 before a new close;
- the fresh v39 preflight differs from eight assets, 14 routes, 28 sides, or
  contains any observe-only scope;
- canonical regime rows are stale, future-derived, incomplete, or UNKNOWN;
- retained exact-v39 routes remain collectively negative after a meaningful
  compatible forward sample, especially after largest-winner removal;
- realized fees, funding, spread, or stop slippage exceed the v41 sensitivity;
  or
- co-triggered losses exceed the modeled v41 stop-wave scenario.

Until those tests are run on the live successor, the evidence supports
progression to v39 at the flat boundary, not a claim of proven profitability.
