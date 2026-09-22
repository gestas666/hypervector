# V90 activation and rollback

> **Executed 2026-09-22 05:01–05:18 UTC.** Live as run `bidirectional-live-1790053305835`,
> fingerprint `c8938787…6b841`. See HANDOFF.md for the activation record, the
> runtime-validation refusal on the first start, and its correction.

Prepared September 21. **Do not execute the activation steps until the operator
approves the corrected protected V90 candidate and allocation.** Preparation and
read-only maintenance are already authorized and completed; the live transition
approval document remains `draft_pending_operator_approval`. This is the existing
profile-change contract, not a new risk/performance gate.

Candidate: `configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml`
Fingerprint: `360de4e99df22b2766a891b034fe76fd58a95a7bf7b1dd77ef9f86dd4b8b6a22` (option B, 2026-09-21; supersedes
`b34fd819…25d2`). **The candidate no longer carries a profit lock**: every hourly
route runs the unlocked `hourly_donchian_20_10_atr20_bidirectional_v1` identity, and
`xyz:TSLA` is added at the screened $500 contract. Read
`docs/reviews/2026-09-21-v90-profit-lock-exit-review.md` for the measured
comparison that drove this, and
`docs/reviews/2026-09-21-v90-profit-protection-readiness.md` for the earlier
protected proposal it replaces. The pending approval maps the old SNDK provider
to the unlocked identity on both sides; SPCX retains no replacement.

## Current state

- Drain `af62626d50cc4b10880109cb6eef735c` completed at 14:00:20 UTC for run
  `bidirectional-live-1789973504608`; its durable marker still blocks ordinary start.
- No live backend or backend supervisor is running. Account flat/order-free at
  the latest unsigned preflight. Refresh that point-in-time proof at activation.
- Read-only roster observer, V89-following checkpoint and watchdog are loaded.
- `v90-launchagents/` contains prepared supervisor and checkpoint definitions;
  neither V90 definition is installed. Keep the observer and watchdog running.
- V90 supervisor owns its child from launch, without adoption. Durable restart
  reservations, five restarts per six hours, technical/clean-exit holds and STOP
  behavior match the tested supervisor. A completed drain/clean stop stays stopped.

## Final activation sequence after approval

1. Validate the exact source manifest, config fingerprint, recommendation hashes,
   retired/replacement scope map and rollback config. Record the actual operator
   approval, actor and timestamp in the draft's required fields; do not fabricate
   approval text or change allocation while filling in authorization metadata.
2. Run the Info-only preflight from the main checkout with `--config` set to V90,
   `--active-config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`,
   and `--checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json`.
   Require fresh flat/order-free/ledger-reconciled venue truth and no active owner.
   Before archival, the completed-marker archive requirement is expected to remain.
3. Back up installed plist definitions and operational state. Preview, then run:

   ```bash
   .venv/bin/python scripts/cohort_transition_drain_archive.py \
     --expected-run-id bidirectional-live-1789973504608 --yes
   ```

   This retains verified identical drain evidence before clearing the blocker.
   Check the current completed run ID again; refuse a mismatch. Do not delete the
   marker manually. Re-run the preflight; approval and archive validation must now
   pass alongside venue/sizing checks. No signed client is needed for preflight.
4. If a supervisor journal exists, verify no owner and retain/archive it under an
   explicit recovery action before a new command identity. Do not reset a live
   restart budget. Verify no unreviewed STOP file, held restart or competing owner.
5. Stop the exact V89 checkpoint service at this boundary, retaining its checkpoint.
   Install the prepared V90 supervisor plist under its original label in
   `~/Library/LaunchAgents`, then `launchctl bootstrap gui/$(id -u) <plist>`.
   Both live-arm flags are present in this prepared command. Verify loaded args,
   its single owned child, prestart backup hash and approved V90 profile identity.
6. On the first complete V90 snapshot, install/bootstrap the prepared V90 checkpoint
   plist. It must use V90, `--follow-latest-run`, and no `--run-id`. Verify a fresh
   V90 checkpoint, reconciled venue state, profile fingerprint and profit-lock
   settings for the three hourly routes. Keep a stopped V89 checkpoint visibly
   historical until this succeeds; it must not masquerade as live V90 health.
7. Verify fresh heartbeat over multiple polls, read-only roster/capture continuity,
   and watchdog health. Capture actual startup duration and polling delay. Startup
   replay can take minutes; a living-but-hung backend alerts rather than being
   blindly killed. Do not SIGKILL the armed backend as a restart experiment.

A plist edit requires bootout/bootstrap, not only `kickstart`. A future abnormal
backend exit consumes the persistent restart allowance; technical exit code 2,
clean exit 0 and STOP are held for explicit recovery. Retries do not conceal a
signing ambiguity or override a profile/venue reconciliation failure.

## Rollback

Before live activation, restore prepared files from their exact backups if
needed; retain new evidence and research history. Once V90 has started, rollback
is a new flat-boundary profile transition: drain with existing exits/protection,
confirm flat/order-free, stop the owner, retain prestart bundle and restore the
reviewed source/config/definitions with an explicit rollback approval and exact
lineage. Do not load V89 over open V90 positions or silently abandon entry-bound
profit-lock plans. Restoring V89 also removes this profit-protection policy, so
that consequence must be part of the operator's rollback decision.
