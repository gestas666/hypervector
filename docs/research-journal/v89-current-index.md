# Current V89 research index

Updated September 8, 2026. This index is research navigation, not a live-state
checkpoint. Read `data/runtime/bidirectional_cohort/latest_checkpoint.json`
for current execution, fills, faults and positions. Do not infer current state
from older HANDOFF entries or an old research-roster checkpoint.

The active goal attachment permits research and proposals, and reserves live
strategy, execution and deployment changes for explicit human approval. Research
records carry `execution_authority=none`; they do not arm or manage orders.

## Current finding and next action

[Chronological shared-account attribution](../reviews/2026-09-08-v89-shared-chronological-stability.md)
is complete. Recorded/adverse results are +$183.56 over the first 28 days and
−$87.44 over the later 20 days, with HYPE contributing −$71.47 in the latter.
The full 48 days earn a modeled $96.12; removing the three largest positive
marked-day contributions gives −$77.62. Confidence is high in the reconciled
arithmetic and low in a causal regime-shift interpretation. Both periods have
already been explored.

Next: `v89_hype_aug26_executable_price_reconstruction_v1`, the historical book
and trade reconstruction specified in that review. It addresses the known
August 26 02:25 source-sensitive entry; it is not a new strategy search or an
assertion that a live order was missed.

## Completed evidence to reuse

| Question | Current evidence and interpretation |
|---|---|
| Shared 48-day source coverage | [Core source fidelity](../reviews/2026-09-07-v89-core-replay-source-fidelity.md); newer verified core inputs exist through September 7. The older annual cache ending July 27 is incomplete as a project inventory. |
| Seven-asset joint cash and marked risk | [Shared marking](../reviews/2026-09-07-v89-seven-asset-shared-marking.md); completed, 176 archive-source trades, six retained sensitivity cases. |
| Recorded candle sensitivity | [Recorded-native study](../reviews/2026-09-07-v89-recorded-native-source-sensitivity.md); 177 modeled trades, first/latest variants agree, one added HYPE long switches between profit and stop loss under slippage assumptions. |
| Current HIP-3 fees | [Fee qualification](../reviews/2026-09-07-v89-current-fee-qualification.md); current metadata is separately qualified and does not establish historical fees. |
| Core inactivity | [Opportunity attribution](../reviews/2026-09-08-v89-core-opportunity-attribution.md); frozen run prefix through 10:40 UTC has zero eligible core entries. This is a bounded observation, not a forecast. |
| HYPE input arithmetic | [Native compression parity](../reviews/2026-09-08-v89-hype-native-compression.md); 907 publications match the independent calculation. Revision 2 corrects the obsolete follow-up, preserving the numerical result. |

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
