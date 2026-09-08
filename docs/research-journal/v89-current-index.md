# Current V89 research index

Updated September 8, 2026. This index is research navigation, not a live-state
checkpoint. Read `data/runtime/bidirectional_cohort/latest_checkpoint.json`
for recorded execution, fills, faults and positions, and verify its age and process liveness. Do not infer current state
from older HANDOFF entries or an old research-roster checkpoint.

The active goal attachment permits research and proposals, and reserves live
strategy, execution and deployment changes for explicit human approval. Research
records carry `execution_authority=none`; they do not arm or manage orders.

## Current finding and next action

Operational update at September 8 14:11 UTC: all seven asset ledgers end in
`STOPPED / operator_stop` at 14:05:33 UTC. The tracked backend, supervisor and
reporter processes are absent; the detached TUI remains open and displays stale
telemetry. Its last checkpoint is from 14:04:48 UTC and cannot establish current
armed execution. Unsigned native core and XYZ reads at 14:11:02–03 UTC report no
positions or open orders. Confidence is high in those observed states; the
shutdown requester remains unidentified. No stop file is currently present.
The generic stop reason also covers termination and terminal-hangup signals.
Evidence: `data/logs/research/bidirectional_cohort/v89_stopped_status_20260908T141101Z/`.
The [stale-display correction](../reviews/2026-09-08-v89-stale-checkpoint-presentation.md)
was [approved and installed](../reviews/2026-09-08-v89-stale-tui-deployment.md),
source `d10b05b`, main source commit `02dd3b9`. The detached monitor was verified as PID
88441 in Terminal window 5958 at 160x50 with all seven assets and nine-view
navigation. At 15:15:54 UTC that monitor is absent and the window reports
`[Process completed]`; its exit requester is unresolved. The approved binary
remains installed. The backend and reporter remain stopped. No process lifecycle
action was taken by the subsequent economic audit. Shutdown attribution remains
unresolved after the bounded log search.

[Chronological shared-account attribution](../reviews/2026-09-08-v89-shared-chronological-stability.md)
is complete. Recorded/adverse results are +$183.56 over the first 28 days and
−$87.44 over the later 20 days, with HYPE contributing −$71.47 in the latter.
The full 48 days earn a modeled $96.12; removing the three largest positive
marked-day contributions gives −$77.62. Confidence is high in the reconciled
arithmetic and low in a causal regime-shift interpretation. Both periods have
already been explored.

The subsequent [HYPE executable-price reconstruction](../reviews/2026-09-08-v89-hype-executable-price.md)
is also complete. All 84 post-publication books have sufficient depth at both
modeled quantities; maximum entry VWAP is $81.888, below the modeled adverse
$81.91002575. Every resulting unrounded 80-bps stop is below the recorded
09:23 candle low. Confidence is high in the bounded arithmetic and low in any
revised-trade claim; this does not establish client fills or venue stop triggers.

The [HYPE mark and historical execution study](../reviews/2026-09-08-v89-hype-mark-trigger.md)
is complete. Ten public-matched fills reconcile an older V61 trade to +$52.769613
net, with different size and exit settings. The 476 vendor marks and 1,899 native
position marks show no observed threshold touch; their gaps prevent a continuous
trigger claim. No current V89 PnL is revised. There is no reason to repeat the
same sparse acquisition without denser evidence.

The [HYPE exit attribution](../reviews/2026-09-08-v89-hype-exit-attribution.md)
is complete. Six recorded-source modeled longs produce −$46.23 nominal and
−$99.26 adverse over 48 days. Price PnL is negative before fees/funding in every
retained case. The August 26 stop-switch explains 91.54% of the nominal/adverse
difference, but excluding it still leaves the other later-period adverse trades
at −$47.69. This is descriptive arithmetic, not a fitted exit recommendation.

The [two-stop execution audit](../reviews/2026-09-08-v89-opening-stop-execution.md)
is complete: SNDK −$7.216071 and SPCX −$3.580442 net. Retained stop-price loss
accounts for −$9.7972 (90.744% of combined net loss), trigger-to-fill movement
−$0.8236, fees −$0.172550 and net funding −$0.003163. Both exits match public
trade identities; sampled marks cross the stop at each fill timestamp. All
2,654 resting-stop observations are consistent. Exact latency remains unresolved.
207 offline tests pass and the source-archive report replays byte-for-byte.
Confidence is high in this arithmetic, low in a causal opening-session diagnosis.

Next: `v89_noncrypto_cash_open_exposure_attribution_20260908_v1`. Preregister
session calendar, local-time window and exposure attribution, then examine the
already registered historical SNDK/SPCX shared-portfolio lifecycles and marks.
Compare opening exposure with other exposure on the same days, retaining asset,
direction and chronological partitions. This is descriptive research, not a
fitted live filter. Prior session feasibility/source studies and the deferred
SPCX crossing filter do not answer this joint exposure question. Keep the sealed
prospective experiment unopened.

Operational note: research import briefly deferred below 8 GiB free space and
resumed automatically. A 180-sample observation at 13:43–13:46 UTC stayed above
11.7 GiB and captured a successful import. It did not reproduce the shortage.
The capacity cause remains unresolved; the mapped-reader proposal measures write
I/O reduction and is not established as a net-space fix.

## Completed evidence to reuse

| Question | Current evidence and interpretation |
|---|---|
| Shared 48-day source coverage | [Core source fidelity](../reviews/2026-09-07-v89-core-replay-source-fidelity.md); newer verified core inputs exist through September 7. The older annual cache ending July 27 is incomplete as a project inventory. |
| Seven-asset joint cash and marked risk | [Shared marking](../reviews/2026-09-07-v89-seven-asset-shared-marking.md); completed, 176 archive-source trades, six retained sensitivity cases. |
| Recorded candle sensitivity | [Recorded-native study](../reviews/2026-09-07-v89-recorded-native-source-sensitivity.md); 177 modeled trades, first/latest variants agree, one added HYPE long switches between profit and stop loss under slippage assumptions. |
| Current HIP-3 fees | [Fee qualification](../reviews/2026-09-07-v89-current-fee-qualification.md); current metadata is separately qualified and does not establish historical fees. |
| Core inactivity | [Opportunity attribution](../reviews/2026-09-08-v89-core-opportunity-attribution.md); frozen run prefix through 10:40 UTC has zero eligible core entries. This is a bounded observation, not a forecast. |
| HYPE input arithmetic | [Native compression parity](../reviews/2026-09-08-v89-hype-native-compression.md); 907 publications match the independent calculation. Revision 2 corrects the obsolete follow-up, preserving the numerical result. |
| HYPE August 26 entry price | [Executable-price reconstruction](../reviews/2026-09-08-v89-hype-executable-price.md); 131 books, 253 public trades, 93 offline tests and exact source-archive replay. The adverse entry exceeds every observed post-publication depth walk; the complete lifecycle remains unresolved. |
| HYPE August 26 marks and actual execution | [Mark qualification](../reviews/2026-09-08-v89-hype-mark-trigger.md); older V61 +$52.769613 reconciled, 30 sampled threshold comparisons unresolved between observations; 81 offline tests and exact archive replay. |
| HYPE losses by exit mechanism | [Exit attribution](../reviews/2026-09-08-v89-hype-exit-attribution.md); all 18 cases and 54 marked-period totals reconcile; six distinct recorded longs, no opposite-signal exits; 22 offline tests and exact archive replay. |

The four September 7 studies were found in
`/Users/gestas/Prototypes/hypervector-v89-portfolio-20260907` and registered in
DuckDB. Their eight review/journal files have now been copied exactly into main
and the current research worktree. Preserve original source-record paths and
hashes; do not append the same revisions under new identities just to copy docs.

## Do not repeat or open early

- `v89_seven_asset_common_window_joint_marking_v1`: withdrawn duplicate proposal.
  The shared study already existed; the completed chronological study is the
  distinct follow-up.
- `v89-quarter-entry-20260908`: faster entry rejected; 177→200 modeled trades
  worsened net and drawdown in all three shared cost cases. Do not reopen without
  new evidence or a changed assumption.
- `v88-hype-onset-missing-early-window-20260906`: no favorable measured relaxation
  lead; do not repeat onset removal from the same evidence.
- `spcx_long_crossing_composition_v1`: completed descriptive split; an entry
  filter remains deferred. This ID does not begin with `v89`.
- Sealed SNDK/Brent prospective experiment: September 8 04:00 through September
  22 04:00 UTC. Do not read early outcomes. Collector health is distinct from
  strategy results.

## Prepared proposals, not deployed

| Candidate | Evidence and remaining boundary |
|---|---|
| Entry dispatch deadline, source `3d204863af40536187df96f161f4874d9fa42166` | [Review](../reviews/2026-09-08-v89-entry-deadline-dispatch-proposal.md); 454 focused tests. Deployment approval is pending; do not re-ask without a relevant update. |
| Bounded memory snapshot reader, source `7a30d04` | Journal `v89-memory-snapshot-20260908`, revision 3; reporting-only deployment proposal remains pending. Keep the rejected earlier candidate distinct. |

These are not deployment authorizations. Existing live process and configuration
identity must be read from current evidence before reporting their state.

## How to find the latest evidence

The authoritative append-only table is
`data/research/market.duckdb:portfolio_research_revisions`. Query the highest
revision per hypothesis across all prefixes, then inspect source-record paths
and verify bytes/SHA-256. A worktree-local document list is not a complete
experiment ledger. Respect the reporter's database writer window; a temporary
lock is not a missing record.

Frozen navigation inventories and copy verification are under
`data/logs/research/bidirectional_cohort/v89_research_navigation_reconciliation_20260908_v1/`.
`journal_inventory.json` is the immutable input used by chronological attribution;
`all_recent_hypotheses.json` also captures non-V89-prefixed work. New revisions
appended after those snapshots must be queried from the database.

Current research source worktree:
`/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.
Shared portfolio/source worktree:
`/Users/gestas/Prototypes/hypervector-v89-portfolio-20260907`.
The main workspace receives reviewed documentation without importing research
source into the live execution code.

Re-read the active goal attachment at each resumed goal turn. Select one
unresolved investigation from current evidence, preserve rejected dispositions,
and update this index when that investigation is completed or superseded.
