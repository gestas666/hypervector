# Stopped-backend checkpoint recovery

Installed commit `12c376d1ad5ddb28bda127a15b9750089d9f8634` preserves current-process
state transitions when checkpoint reporting recovers older trade history.
Candidate commit: `e894b264976710c5541bd30842db05ddf6091ddd`.
High confidence in the diagnosed defect comes from the actual failing checkpoint
inputs, an offline regression and successful reconstruction from unchanged native
ledgers. This is a reporting repair; it does not establish strategy profitability.

## Observed failure and repair

The original backend's last heartbeat was at September 16 **13:38:31.697664 UTC**.
All seven asset journals subsequently recorded `STOPPED`, with `operator_stop`
and no recorded fault. The original financial processes were absent. The stop's
human intent and exact initiating mechanism remain unconfirmed.

The updated read-only monitor opened successfully and showed `LEV C/V`, but its
checkpoint reporter repeatedly failed with `checkpoint asset state cutoff mismatch`.
Captured validator inputs showed ETH/SOL/HYPE stopped, BTC/SPCX/SNDK flat and Brent
open. Assets requiring compatible execution history had their later state
transitions removed by the economic cutoff; the current-run fast path retained
those same transitions for the other assets. This produced a false mixed lifecycle.

The compact asset projection now has an explicit, default-off option to retain
post-cutoff state transitions belonging to the selected run. Both checkpoint
history recovery paths enable it. Later funding, position, order and foreign-run
rows remain excluded by the projection. Audit consumers independently retain
their original economic cutoff. The consistency validator is unchanged: a partial
stop, incompatible state or unprotected open position still prevents publication.

The repaired native checkpoint reports all seven workers stopped and retains the
last economic snapshot: Brent short **4.9**, stop order **546683530230** present;
the six other assets flat. This dated ledger evidence is distinct from current
venue verification. An unsigned venue observation completed at **13:55:29 UTC**
separately found only Brent short 4.9 at 101.88, **10x isolated**, and an open 4.9
buy reduce-only stop-market order at 103.18. The before/after observations agreed
on size and leverage; sequential API responses are not an atomic snapshot.

## Validation and evidence

- Final baseline reproduction: **5 failed, 3 passed**. The protected inherited
  position reproduced the observed mismatch; both compacted modes lost its stop.
- Candidate and installed source: **150 tests passed each**, without network
  calls. Coverage across the three affected modules is **94%**; recovery and
  snapshot selection each have **100% statement and branch coverage**. The new
  lifecycle-retention branch is covered. Existing projection validation branches
  account for the remaining gaps.
- Controls include protected and unprotected stopped positions, partial stops,
  faults, foreign-run transitions, default-off behavior and exclusion of later
  financial events. The synthetic position's exact inherited funding is retained.
- Actual ledger reconstruction completed successfully. All **11 source ledger
  hashes** matched before and after. No historical ledger was rewritten.
- Ruff and whitespace checks passed. Installation changed three reporting modules,
  added one test file and preserved **5,631 other tracked file contents**.
  The installed TUI binary hash remains
  `52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84`.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_stopped_checkpoint_20260916_v1/`.
`red_final_fixture.txt` and `green_final.txt` are the definitive candidate
comparison. Earlier retained attempts exposed a fixture without a matching stop,
an incorrect open-versus-closed funding assertion and a baseline import-path
mistake; these were corrected before the final baseline and candidate runs.
`native_checkpoint_validation.json` authenticates the actual reconstruction.
The separate unsigned venue receipts are in
`data/logs/research/bidirectional_cohort/v89_backend_stop_20260916_v1/`.

## Installed monitor

The owned read-only monitor was quit normally and reopened at **14:13:09 UTC**.
Its new checkpoint at **14:14:05.757970 UTC** correctly classified all seven
workers stopped. Native Terminal text at **14:14:18 UTC** showed `BACKEND STOPPED`,
`STOPPED SNAPSHOT`, `LEV C/V`, Brent `10x/10x` and `LOCAL EXITS OFF`. Position and
strategy panes retained explicit stale-backend labels. The original financial
backend remained absent throughout. Current monitor processes are CLI 79095,
supervisor 79099, reporter 79551 and TUI 79552; birth times and arguments are
retained in `monitor_processes_after.json`.

Two further reporter checkpoints at **14:14:47.724316** and **14:15:29.975669 UTC**
were retained byte-for-byte. Both passed freshness and all-stopped assertions;
Terminal acceptance at **14:15:41 UTC** confirmed the leverage and stopped labels
with no stale-checkpoint label. `monitor_acceptance.json` records both hashes and
their independent observation ages. The stale-backend labels correctly remain.

## Scope, alternatives and rollback

Keeping the previous projection leaves the stopped-run checkpoint permanently
stale whenever asset history requirements differ. Relaxing the consistency check
would hide unresolved mismatches. Retaining explicitly scoped process evidence
repairs the information loss while preserving the existing publication checks.
The monitor can refresh account reporting after the backend stops, but it cannot
generate new strategy decisions or manage local exits. Read the backend and
decision ages independently of checkpoint generation time.

Prior source is backed up at
`data/backups/cohort_stopped_checkpoint/preinstall_20260916T141148087629Z/`.
The recorded reverse patch passes applicability checks. Rollback requires matching
installed bytes, reversing only this repair and reloading only the owned read-only
monitor. The original financial backend was not started, stopped or signalled.
The separate `e49f2fa` backend lifecycle-receipt proposal remains uninstalled and
subject to its already-pending approval.

A missed terminal transition, financial row crossing its cutoff, concealed partial
stop, changed ledger hash or fresh-checkpoint label masking stale strategy evidence
would falsify acceptance and reopen this repair. Full strategy qualification and
the stopped session's cause remain separate outstanding investigations.
