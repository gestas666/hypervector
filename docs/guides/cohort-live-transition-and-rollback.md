# Cohort live transition and rollback

This guide covers how the shared cohort backend changes profile, restarts and
rolls back.

- **Flat boundaries only.** A profile change happens only at a verified flat,
  order-free venue boundary.
- **No forced closes.** Nothing here closes positions to create that boundary.
- **No hot mutation.** Nothing here changes a running strategy in memory.

Only the steps marked **ARMS** can lead to signed orders. Each one needs an
explicit operator instruction given at that moment. A documented command is not
that instruction.

## Paths and the current example

| Item | Value |
| --- | --- |
| Active profile (example) | `configs/multi_asset_growth_first_5000_review_fixes_v95.toml` |
| Active fingerprint | `dd779cce74568e4ba6963d1a19810a7fbcaa7f4279e40f45be83f12286339420` |
| Rollback profile | `configs/v95-to-v94-rollback-20260927-v1.toml` (fingerprint `5fe5a9de…`) |
| Rollback approval | `docs/live-approvals/v95-to-v94-rollback-20260927-v1.json` |
| Cohort ledger | `data/live/bidirectional_cohort/decisions.jsonl` (plus per-symbol journals) |
| STOP file | `data/live/bidirectional_cohort/STOP` |
| Drain marker | `data/live/bidirectional_cohort/transition_drain.json` |
| Live checkpoint | `data/runtime/bidirectional_cohort/latest_checkpoint.json` |
| Backups | `data/backups/bidirectional_cohort/` (`prestart_*`, `transition_drains/`) |
| launchd agents | `local.hypervector.cohort.supervise`, `.checkpoint`, `.watch`; `local.hypervector.research.roster_observer` |

The shell examples use these variables:

```bash
ACTIVE=configs/multi_asset_growth_first_5000_review_fixes_v95.toml
CANDIDATE=configs/<candidate-profile>.toml
CKPT=data/runtime/bidirectional_cohort/latest_checkpoint.json
HV=".venv/bin/python -m hypervector"
```

A candidate whose fingerprint differs from the last recorded run must name its
operator approval in `[runtime] transition_approval`. The start refuses before
it builds any client when that approval is missing or does not match.

A same-profile restart needs no new approval. If the implementation identity
changed (any edit under `src/`), the start still records a new pre-start bundle,
and it still needs the operator's go-ahead.

## Flat-boundary predicate

Steps 4 and 6 reuse this predicate. It succeeds only when every asset is
terminal and flat, holds no owned orders, and shows zero faults:

```bash
FLAT='.lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    .final_state == "FLAT" and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all)'
```

Success is exit 0 with JSON `true`. Any of these refuses the transition:

- an open position;
- an owned order;
- a fault;
- unavailable drain evidence;
- an unavailable venue checkpoint.

## Procedure: change profile

### 1. Back up the active implementation

```bash
$HV live backup --config "$ACTIVE"
$HV live backup-verify --bundle <exact printed bundle path>
```

`live backup` loads the profile in observe mode. It captures the bounded
Hypervector and backtest-lab source set that a live start would hash, together
with the ledgers, and restore-verifies every archive.

- It is credential-free and may run while the backend is live.
- It exits 0 when verified and 2 when refused.
- Require all of these in its output:
  - `status=verified` and `execution_authority=none`;
  - the active `profile_fingerprint`;
  - `strategy_changed_from_latest_ledger=false`;
  - a nonzero `implementation_file_count` and a nonempty `implementation_sha256`.

Keep the exact printed path. This baseline does not replace the pre-start bundle
that the next start makes for itself.

### 2. Validate the candidate offline

```bash
$HV live validate --config "$CANDIDATE" --mode live --equity <USD>
$HV live preflight --config "$CANDIDATE" --active-config "$ACTIVE" --checkpoint "$CKPT" --out preflight.json
```

`live validate` reproduces the runner's construction-time checks without
credentials. Its exit codes:

| Code | Meaning |
| --- | --- |
| 0 | accepted |
| 1 | runner objection |
| 2 | config refusal |
| 3 | book-level advisory; report-only, and the runner never reads it |

`live preflight` reads only the public wallet. It exits 0 ready, 3 not ready
and 2 refused. Resolve every 1 or 2 before going on.

### 3. Request the drain

```bash
$HV live request --inbox <active-run operator inbox> --run-id <active run id> \
  --profile-fingerprint <active fingerprint> --action transition_drain --symbol MULTI
# inspect the dry run, then publish (live authority):
$HV live request ... --action transition_drain --symbol MULTI --submit --enabled --i-accept-live-risk
```

Publishing writes no venue order. The armed backend then:

- validates the run and profile identity and persists the request;
- withholds new entries on flat symbols;
- keeps automatic exits, maximum-hold exits, manual closes and venue-native
  protection running.

It never activates a candidate. After acceptance the checkpoint must show
`transition_drain.status == "active"`. A missing or null state means the
projection is stale; it does not mean the drain is inactive.

### 4. Prove the flat boundary and confirm the backend stopped

```bash
jq -e "$FLAT"' and .transition_drain.status == "completed"' "$CKPT"
pgrep -lf 'multi_asset_bidirectional_live(\.py)?( |$)'              # backend: expect nothing
pgrep -lf 'multi_asset_bidirectional_live_checkpoint(\.py)?( |$)'   # checkpoint writer: expect nothing
```

When the drain completes, the backend stops itself after its final snapshot.
Do not kill a process. Stop any separately owned checkpoint writer only after
the backend has stopped. Never run two writers against the same output.

### 5. Archive the completed drain

```bash
$HV live drain-archive --expected-run-id <drained run id>          # preview
$HV live drain-archive --expected-run-id <drained run id> --yes    # archive and clear the start blocker
```

The command takes exclusive runtime ownership. It refuses (exit 2) any of:

- a running backend;
- an incomplete drain;
- an identity mismatch;
- an archive collision.

It preserves the marker bytes under
`data/backups/bidirectional_cohort/transition_drains/` before it clears the
blocker. `<drained run id>` is the marker's `run_id` field.

### 6. Re-check the boundary against the candidate

```bash
$HV live checkpoint --config "$CANDIDATE" --once --no-current-run-only --venue-portfolio
jq -e "$FLAT"' and .configuration_generation.restart_state == "candidate_flat_no_orders"' "$CKPT"
$HV live check --config "$CANDIDATE"
```

`live check` must show no blocker other than the two authority flags.

- **STOP file.** If it shows the STOP file, the operator removes exactly that
  file. Never remove a ledger, order-command, checkpoint or backup file.
- **Drain marker.** If it still shows the drain marker, go back to step 5.

### 7. Start the candidate (ARMS)

Choose one of these, on an explicit operator instruction:

- **Supervised.** The operator copies the installed supervise plist, edits only
  its `--config` argument, then enables and kickstarts the agent:

  ```bash
  launchctl enable gui/$(id -u)/local.hypervector.cohort.supervise
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.hypervector.cohort.supervise.plist
  ```

- **Direct, with no crash recovery:**

  ```bash
  $HV live start --config "$CANDIDATE" --enabled --i-accept-live-risk
  ```

Before it builds an authenticated client, the backend takes the singleton lock.
It then writes, decompresses and hash-verifies an immutable pre-start bundle:
the bounded execution sources, `pyproject.toml`, `uv.lock`, the profile and the
ledgers. The log shows one line like this:

```text
pre-start backup verified: path=... manifest_sha256=... strategy_changed=yes
```

### 8. Verify the new pre-start bundle

```bash
$HV live backup-verify --bundle data/backups/bidirectional_cohort/prestart_<exact path from the log>
```

Never guess the directory name. Require `"status": "verified"`, the previous
and target profiles you expect, a nonzero `implementation_file_count` and a
nonempty `implementation_sha256`. A missing implementation identity is a
refused start, not a warning.

### 9. Accept the new run

```bash
$HV live checkpoint --config "$CANDIDATE" --follow-latest-run    # or let the checkpoint agent publish
$HV live monitor --config "$CANDIDATE" --follow
$HV live audit --run-id <new run id> --out-dir data/logs/cohort-audits
```

Require all of these:

- the candidate's runtime profile id and fingerprint;
- lifecycle `running_consistent` with zero asset faults;
- the expected executable and observe-only routes;
- no position or owned order inherited from the previous run;
- a `prestart_backup` object in the run's `configuration_identity` with
  `status=verified` and the same bundle, manifest hash and implementation
  identity.

On the first new position, require all of these:

- a nonzero venue stop OID;
- a matching signed venue size;
- the configured isolated leverage;
- a liquidation price;
- fees and funding;
- the entry regime and provider identity;
- acknowledgement and slippage telemetry.

Missing protection or a position disagreement is a live fault.

## Procedure: same-profile restart from a stopped book

Use this when the backend was stopped through a completed drain and the STOP
file. The book is flat and the profile is unchanged.

1. **Rehearse offline.** No authority is needed and nothing starts.

   ```bash
   $HV live check --config "$ACTIVE"                 # expect: STOP and drain-marker blockers only (plus the flags)
   $HV live validate --config "$ACTIVE" --mode live --equity <USD>
   $HV live backup --config "$ACTIVE"
   $HV live backup-verify --bundle <printed path>
   $HV live drain-archive --expected-run-id <run_id in transition_drain.json>   # preview only
   ```

2. **Get the go-ahead.** Restarting needs the operator's explicit instruction.
   Then run `live drain-archive ... --yes`; the operator removes the STOP file.
3. **Confirm flat.** Publish one checkpoint with `--no-current-run-only
   --venue-portfolio` and require the flat predicate.
4. **Start and accept.** Run steps 7 to 9 with `$ACTIVE`.

## Rollback

There is no hot rollback. Keep managing any open lifecycle under its recorded
contract until the flat predicate passes. Then:

```bash
$HV live rollback-profile --current "$ACTIVE" --verify configs/v95-to-v94-rollback-20260927-v1.toml
```

That verifies the approved rollback pair and dry-runs its start offline. It
exits 0 when accepted and 2 when refused, and it starts nothing. Then run steps
3 to 9 with the rollback profile as the candidate.

To author a new rollback pair, use author mode:

```bash
$HV live rollback-profile --current "$ACTIVE" --target <profile.toml> --name <name> \
  --operator-approval "<the operator's exact words>"
```

It writes the profile under `configs/` and the approval under
`docs/live-approvals/`.

**Profile-only rollback.** Copy the installed plists and edit only the intended
`--config` arguments. Preserve `PYTHONPATH`, restart opt-in, endpoint URLs and
other installed settings. Do not regenerate installed definitions with
`print-launchd`: the generator is not an export of the installed configuration.
Validate copies with `plutil -lint` and inspect their differences locally
without printing endpoint secrets. Record hashes in the deployment manifest.

If a start fails before the `pre-start backup verified` line, no authenticated
client was built. Inspect the refusal and run `live backup-verify`; never bypass
the gate. If it fails after the configuration identity was recorded, use the
venue-backed checkpoint to tell a technical startup fault from a position or
order mismatch.

There is no automatic restore into live paths, because it could overwrite newer
venue-reconciled truth. `live backup-verify` proves a bundle can be recovered.
Any actual restore goes into a new empty inspection directory first, and needs a
separate operator decision.

## Interrupted drain

If the backend exits while a drain is active, an ordinary start stays refused.
Do not archive the active marker, and do not start a candidate. Recover only the
same active profile, with fresh explicit live authority:

```bash
$HV live start --config "$ACTIVE" --resume-transition-drain --enabled --i-accept-live-risk   # ARMS
```

The recovery start:

- gets a new run ID, but keeps the original request and origin run;
- increments `resume_count` and records `last_resumed_at_utc`;
- starts with entries already withheld.

Before it rebinds the marker, it captures and hash-verifies the old marker bytes
in its pre-start bundle. Each of these refuses recovery before any
authenticated client exists:

- a missing marker;
- a completed marker;
- a profile mismatch;
- a backup failure;
- a reused run identity.

**Under supervision.** A crash or reboot during an active drain leaves the
supervisor held with `live_start_refused_fail_closed`. Host-restart opt-in does
not supply `--resume-transition-drain`, and `live supervisor resume` does not
apply to this hold. With explicit authority to resume the drain:

1. Disable and unload the supervise agent, and verify that its backend stopped.
2. Back up and archive the restart journal.
3. Recover with the command above, or with a backed-up copy of the supervise
   plist whose child arguments add `--resume-transition-drain`.

## Host reboot

```bash
$HV live supervisor resume                                        # dry run: checks only
$HV live supervisor resume --yes --enabled --i-accept-live-risk  # ARMS: archive the restart journal, kickstart supervise
```

`resume` refuses (exit 1) in each of these cases:

- a STOP file is present;
- a backend is running;
- the hold is not a host-restart class;
- the hold does not predate this boot;
- the supervise agent is unloaded or disabled.

`--yes` without both authority flags exits 2. A durable operator stop is the
STOP file, or `launchctl disable` before any bootout. A bare bootout followed by
a reboot can auto-resume when host-restart resume is opted in.

## What invalidates a transition

Any of these:

- a changed candidate fingerprint;
- a position or owned order at the boundary;
- incomplete backup verification;
- two checkpoint writers;
- a missing fresh run identity;
- a protection fault on the first position.

Strategy performance is reported evidence, never a technical start gate.
