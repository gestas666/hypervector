# Cohort live transition and rollback

This runbook changes the current multi-asset cohort only from a verified flat
venue boundary. It does not close positions to create that boundary and does
not hot-mutate a running strategy.

## Frozen transition identity

- Running profile: `configs/multi_asset_bidirectional_canary.toml`
- Running fingerprint: `c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b`
- Candidate profile:
  `configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml`
- Candidate fingerprint: `750b2df619db858446ded8dd96ce4f679607c6965c789b0fdfcec56a2090fc4e`
- Candidate file SHA-256:
  `b97217b921fbd73d8ac9ac76b4ffe3a594a91890b9d8bf6945b05625ec06997b`
- Candidate effect: only bidirectional Hulk/BTC and canonical
  HYPE-breakout/HYPE may execute. Every other configured provider-symbol pair
  remains observe-only. Canonical HYPE rises from `$25` to `$75` maximum
  notional at 5x isolated and retains the existing eight-hour soft hold with
  regime-supported extension to a 24-hour hard maximum. No automatic restart.

If either file fingerprint changes, stop and regenerate this runbook's evidence.
Do not substitute the fixed-eight-hour or allocation-only candidate. Those
profiles remain preserved comparators, not the selected restart identity.

The latest portfolio decision is
`docs/reviews/2026-08-05-evidence-routed-next-flat-portfolio.md`. It preserves
the current HYPE lifecycle contract so the next run changes allocation and
routing scope without simultaneously changing exit semantics. The earlier
two-trade fixed-boundary comparison remains contradictory historical evidence;
it is not strong enough to establish an exit edge or overwrite the selected
contract. Portfolio-edge confidence remains low-to-medium until profile-matched
live closes and missed-opportunity evidence update it.

The credential-free active implementation baseline is independently verified
at
`data/backups/bidirectional_cohort/prestart_20260805T180123.525318Z_c992cb2f958e`.
Its manifest SHA-256 is
`694c31c42ca38b7ee22348808474d05b5db91901d0dd8cc42a2795544e01c875`;
it contains 1,163 implementation files with composite SHA-256
`ac3bd00c860181c13c509e101ac334c592339e286ffe8dce39820c2b90e99810`.
This baseline does not replace the mandatory fresh pre-start bundle.

<!-- cohort-transition-contract:start -->
```json
{
  "candidate_path": "configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_routed_hype75_v9",
  "candidate_profile_fingerprint": "750b2df619db858446ded8dd96ce4f679607c6965c789b0fdfcec56a2090fc4e",
  "candidate_file_sha256": "b97217b921fbd73d8ac9ac76b4ffe3a594a91890b9d8bf6945b05625ec06997b",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hype_breakout_onset_bidirectional_v1|HYPE"
  ],
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

## 0. Capture the active implementation before editing

Before changing an active strategy config or any shared Python execution
source, publish a credential-free source baseline:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_bidirectional_canary.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab
```

The command loads the profile in observe mode, discovers the same bounded
Hypervector and backtest-lab source set used by live startup, writes an
immutable pre-start-format bundle, and immediately restores and SHA-256
verifies every archive. It neither imports credentials nor creates a venue
adapter. It may run while the backend is live because it performs no runtime or
order mutation.

Require `status=verified`, `execution_authority=none`, the active profile
fingerprint, `strategy_changed_from_latest_ledger=false`, a nonzero
implementation file count, and a nonempty implementation SHA-256. Preserve the
exact printed path. Independently verify it with
`scripts/cohort_prestart_backup_verify.py` before editing.

This is an implementation/profile baseline, not a live-start authorization or
an atomic venue-state checkpoint. Its run fingerprint is observe-mode by
design, and append-only ledgers may continue growing after their exact captured
prefix. The later candidate activation must still create and journal its own
mandatory live pre-start bundle in Step 5.

## Bootstrap limitation for the current legacy process

The process started on 2026-08-04 does not contain the transition-drain code
described below. It cannot be upgraded in memory, and missing drain telemetry
must remain `unavailable`. Its one-time cutover therefore still requires an
operator-observed flat/no-owned-orders checkpoint followed immediately by the
legacy STOP request. If a new entry appears before shutdown, the transition is
aborted and that lifecycle remains managed under the old contract. Do not
pretend the drain protected this first cutover, and do not stop the legacy
process while it has an open position merely to load the new code.

## 1. Request a drain on a drain-capable run

On TUI screen 7, select `TRANSITION DRAIN`, press Enter, inspect the explicit
confirmation, and press `y` only with current operator authorization. The Rust
TUI writes no venue order. The armed Python backend validates the exact run and
profile identity, persists the request, withholds new entries on flat symbols,
and continues automatic exits, maximum-hold exits, manual closes, and
venue-native protection. It never activates or starts a candidate profile.

The checkpoint must report `transition_drain.status == "active"` after backend
acceptance. A missing/null state means the run is legacy or the projection is
stale; it is not evidence that the drain is inactive.

### Recover an interrupted active drain

If the Python backend exits while the durable drain is active, an ordinary
start remains refused. Do not archive the active marker and do not start a
candidate profile. Recover only the exact active profile with fresh explicit
live authority:

```bash
.venv/bin/python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config <exact-active-profile>
```

Recovery creates a new process run ID but preserves the original drain request
and origin run. It increments `resume_count`, records `last_resumed_at_utc`, and
starts with entries already withheld. Before rebinding the marker, startup must
capture and hash-verify its old run-bound bytes in the mandatory pre-start
bundle. A missing marker, completed marker, profile mismatch, backup failure,
or reused run identity refuses recovery before authenticated adapter creation.

After recovery, require the checkpoint to show `status == "active"`, the new
run ID, the unchanged origin run and request ID, and the incremented resume
count. Then continue with the flat/no-owned-orders proof below. Recovery is a
continuation of the drain contract, not permission to activate the candidate.

### Supervised drain interruption

A crash or reboot during an active drain can leave the supervisor held with
`live_start_refused_fail_closed` and refusal text indicating that transition
drain evidence remains. Host-restart opt-in does not supply the missing
`--resume-transition-drain` flag.

Keep the watch loaded and retain the active drain marker. Check fresh unsigned
venue state and verify process ownership; a stale checkpoint is insufficient.
With explicit authority to resume the existing drain, disable and unload the
supervisor, verify its backend is stopped, then back up and archive its restart
journal. Do not use the ordinary host-restart resume helper for this hold.

Recover the exact active profile using the command above, or a backed-up copy
of the installed supervisor plist whose child arguments add
`--resume-transition-drain`. The direct command has no supervisor crash recovery.
For supervised recovery, preserve installed environment settings and restore
service enablement only as part of the authorized resume. Verify the unchanged
request and origin run, new run ID and incremented resume count. Archive the
drain marker only after its completed, flat and order-free boundary is proven.

## 2. Prove the flat boundary and stop the backend

### Drain-capable run

Use the continuously published, venue-backed checkpoint:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    .final_state == "FLAT" and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .transition_drain.status == "completed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Success is exit code zero and JSON `true`. Any open position, owned order,
fault, unavailable drain evidence, or unavailable venue checkpoint refuses the
transition. Candidate identity is not part of this running-process gate because
the selected profile must not be staged while armed. Drain completion makes the
backend stop itself only after the final completed snapshot.

### Current legacy run

The current process reports `transition_drain.status == "unavailable"`. Wait
for the same fresh checkpoint to prove every asset flat, signed size zero, no
owned orders, and zero faults:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    .final_state == "FLAT" and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .transition_drain.status == "unavailable"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

On JSON `true`, immediately request the exact configured legacy STOP path:

```bash
touch data/live/bidirectional_cohort/STOP
```

This legacy sequence has an entry race because the in-memory process cannot
withhold new entries. Re-read the final venue-backed snapshot after shutdown.
If any position or order appeared, do not start the candidate; recover the
exact old profile and its recorded lifecycle instead.

For either path, confirm both wrapper and Python backend processes have exited:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live.py'
```

Expected output is empty. Do not kill a process. The append-only ledgers and
completed drain evidence remain in place. Quit the monitor TUI after the backend
has stopped, then require the following checkpoint-writer check to be empty:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'
```

Do not publish the manual candidate checkpoint while the monitor-owned sidecar
is still writing the same output file.

## 3. Archive the completed drain recoverably

This step applies only to a drain-capable run with a completed marker. The
current one-time legacy cutover has no marker and skips directly to Step 4.

Preview first using the exact run identity shown by the checkpoint:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>
```

The preview must show the intended completed marker and archive destination.
Then repeat with `--yes`. The command refuses an active backend, an incomplete
drain, an identity mismatch, or an archive collision. It preserves the exact
bytes below `data/backups/bidirectional_cohort/transition_drains/` before
clearing the live start blocker.

## 4. Reconfirm state and clear only a legacy stop request

Publish one final report-only checkpoint using the candidate configuration:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Repeat the flat/no-order/health predicates from Step 2. For the one-time legacy
bootstrap only, drain state will be unavailable; preserve that fact in the
journal. Additionally require the report-only candidate projection to bind the
exact selected fingerprint:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    .final_state == "FLAT" and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .configuration_generation.restart_state == "candidate_flat_no_orders" and
  .configuration_generation.current_profile_fingerprint ==
    "750b2df619db858446ded8dd96ce4f679607c6965c789b0fdfcec56a2090fc4e"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

If the predicates pass and no backend or checkpoint-writer process exists,
remove exactly the inspected ephemeral legacy stop request:

```bash
rm data/live/bidirectional_cohort/STOP
```

Do not remove any ledger, order-command, checkpoint, or backup file.

## 5. Start the candidate through the unified launcher

This is the only live-arm command in this runbook:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml \
  --enabled --i-accept-live-risk
```

After acquiring the singleton lock, the backend must create, decompress, and
hash-verify an immutable pre-start bundle before constructing authenticated
Hyperliquid adapters. The launcher allows 180 seconds for this preparation and
fresh telemetry. The bundle must include the complete bounded Python execution
source set from Hypervector and its local backtest-lab provider dependency, plus
`pyproject.toml` and `uv.lock`; its manifest binds those bytes through an
implementation file count and composite SHA-256.

The backend log must contain one line like:

```text
pre-start backup verified: path=... manifest_sha256=... strategy_changed=yes
```

Copy the exact printed bundle path and independently verify it:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

Do not guess the directory name. Verification must return JSON with
`"status": "verified"`, previous profile `multi_asset_bidirectional_canary_v2`,
target profile `multi_asset_bidirectional_evidence_routed_hype75_v9`, a
nonzero implementation file count, and a nonempty implementation SHA-256.
Missing implementation identity is a refused new start, not a warning.

## 6. Accept the new run identity before accepting entries

The TUI and checkpoint must show:

- runtime profile `multi_asset_bidirectional_evidence_routed_hype75_v9`;
- runtime fingerprint `750b2df6...` matching the candidate;
- lifecycle `running_consistent` and zero asset faults;
- Hulk/BTC and canonical HYPE-breakout/HYPE labeled bidirectional canary;
- every Range Onset row, Source Follow/BTC, and Hulk/ETH, Hulk/SOL, and
  Hulk/HYPE labeled observe-only;
- HYPE canonical maximum notional `$75` at isolated 5x;
- HYPE canonical maximum hold set to an eight-hour soft boundary with
  `extend_while_regime_supported` and a 24-hour hard maximum;
- no inherited position or owned order from the prior flat run.

The new run's authoritative `configuration_identity` event must also contain a
`prestart_backup` object with `status=verified`, the exact bundle and manifest
paths, the manifest SHA-256, strategy-change flag, nonzero implementation file
count, and composite implementation SHA-256. The TUI restart-profile page must
render `PRESTART VERIFIED` with matching manifest/source hash prefixes and file
count. Re-run the independent verifier against that exact bundle if any value
disagrees. A legacy `PRESTART BACKUP UNAVAILABLE` display is valid only for a
process that demonstrably started before this journal field existed; it is not
acceptable for the new candidate run.

On the first new position, require a nonzero venue stop OID, matching signed
venue size, isolated 5x leverage, liquidation price, fees, funding, entry
regime, provider identity, and acknowledgement/slippage telemetry. Missing
protection or position disagreement is a live fault, not a display issue.

## Rollback

There is no hot rollback. Keep managing any open candidate lifecycle under its
recorded contract. Once the same flat/no-owned-orders predicate passes:

1. stop the candidate normally using Steps 2 and 3;
2. retain and verify its pre-start bundle and append-only ledgers;
3. restart through the unified command with
   `configs/multi_asset_bidirectional_canary.toml`; and
4. verify the old fingerprint and protection exactly as in Step 6.

If candidate startup fails before the `pre-start backup verified` line, no
authenticated adapter should have been constructed. Inspect the refusal and
run the backup verifier; do not bypass the gate. If it fails after fresh
configuration identity, use the venue-backed checkpoint to distinguish a
technical startup fault from a position/order mismatch.

Automatic restoration into live paths is intentionally unavailable because it
could overwrite newer venue-reconciled truth. The backup verifier proves exact
recoverability; any actual restore must target a new empty inspection directory
first and requires a separate explicit operator decision.

## Evidence that updates this runbook

The transition is invalidated by a changed candidate fingerprint, a position or
owned order at the boundary, incomplete backup verification, two checkpoint
writers, a missing fresh run identity, or any first-position protection fault.
The strategy selection is updated by reconciled after-cost outcomes and missed
opportunities, including side coverage, concentration, realized friction, and
regime/order-book context. Performance remains reported evidence rather than an
implicit technical startup gate.
