# V88 transition and rollback — pending approval

This is the executable procedure accompanying [the V88 proposal](../reviews/2026-09-05-v88-live-proposal.md). It grants no authority. The original working tree is clean at `4fae13c`; the isolated September source is on `agent/evidence-overhaul-20260905`. No live process is running at package preparation.

The candidate profile fingerprint is `06e90a0c59b4b767fd14a61f3927553fc00b3017405193170101531204761d5f`. The prior V86 fingerprint is `f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733`, run `bidirectional-live-1788585501070`. Exact provider names, directions and effective risk settings are in the proposal and TOML. Approval of this procedure includes deployment of the tested code/TUI and report-only sidecars; it does not authorize 2× size, new assets or subsequent strategy revisions.

## Preserved recovery evidence

- September baseline commit: `fac03696ed035e22815c49d6a9f7e491b2465e88`.
- Original-root archive: `data/backups/bidirectional_cohort/overhaul_v86_fac0369_source_20260905_v1.tar.gz`, SHA-256 `c1ae6430027324580457469c4d8839f55042651047a11c1f2bcc4831940d80a1`. All 4,814 tracked file/symlink Git blobs were verified without extracting over the workspace.
- Final V86 flat ledger archive: `data/backups/bidirectional_cohort/legacy_STOP_v86_bidirectional-live-1788585501070_overhaul_20260905.json`, SHA-256 `ee352d5a7b9ca2d58ea83893e1eb3c5c7fc149afe3f1c25c49e4504f7b61b031`. Archival did not write a STOP request or order.
- The existing live launcher creates and verifies a new prestart bundle containing the exact current source, prior/candidate config, approval and ledger evidence before constructing live clients. That final bundle necessarily follows approval; its path and manifest hash must be recorded before startup acceptance.

## Approved execution sequence

1. Obtain an explicit operator response approving this exact proposal and source revision. Preserve its verbatim scope and timestamp in the candidate's declared approval document, `docs/live-approvals/v86-to-v88-four-core-evidence-pending-20260905-v1.json`. Validate it with the existing profile-change validator; a draft or invented approval must fail.
2. Recheck both source trees, source/config hashes and running process ownership. Unexpected source changes require reconciliation. Preserve the original Git commit and data. Fast-forward the clean original tree to the approved isolated revision; do not reset, amend or overwrite unrelated work. Synchronize its locked runtime and build the tested release binary.
3. Run the candidate public-wallet-only preflight with the explicit prior V86 config and original live checkpoint. Require all four retained and three retired symbols flat, no open orders, reconciled ledgers, exact venue constraints/fees and validated transition archive. Preserve a new immutable output. The earlier snapshot cannot substitute for this fresh pre-arm check.
4. Verify and archive any existing STOP/control file with its original contents before clearing it for the explicitly approved start. Do not erase history or alter a still-owned live lifecycle. Let the existing launcher create the immutable final prestart bundle and verify its identity.
5. From `/Users/gestas/Prototypes/hypervector`, execute only after approval:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --config configs/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --mode live --enabled --i-accept-live-risk
```

The supervisor owns its backend and checkpoint. Quitting this supervised TUI stops its owned backend; it is not a detached monitor. Record all owned process handles, run ID, source identity, checkpoint and logs. A separately opened monitor must not be confused with the supervisor.

6. After the first fresh exact V88 live checkpoint, start the report-only improvement loop:

```bash
uv run python scripts/cohort_improvement_monitor.py \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --decision-overrides configs/research/cohort_improvement_decision_overrides_v88.json \
  --out data/runtime/bidirectional_cohort/latest_v88_improvement_digest.json \
  --history data/live/research/v88_continuous_improvement.jsonl \
  --interval-seconds 120
```

This loop validates source/profile hashes, rejects stale checkpoints, preserves the last valid report on failure and appends material changes. It cannot submit orders, resize, retune, promote or retire a route. Bind each prospective native lifecycle investigation to the actual new run and cutoff before reviewing its outcomes; use the existing exact-route watcher with the specified long/short side. The prelaunch observer has no live lifecycle audit and must not be passed off as this live checkpoint. Stop the owned loop when the backend stops; stale retained reports remain historical.

## Post-start acceptance and continuing review

Require fresh, matching run/profile/source identity, four provider rows, source timestamps within each contract, venue reconciliation, structured logs, and no unexpected orders or exposures. A post-start zero-entry interval is an operational observation, not an economic rejection. Capture all nine TUI screens against the live checkpoint; observer acceptance cannot establish live protection or fill behavior.

On the first attributable event for each route, reconcile decision, routing, entry age/reference, venue rounding and partial fills, protective-order acknowledgement, hold/recipe action, exit, fees and funding. Preserve immutable audits and revisions. The existing generic monitor ranks opportunities and maintains hypotheses; the research agent must investigate material changes and source mismatches rather than repeatedly polling unchanged results. HYPE native execution/hold fidelity is the initial highest-value investigation. One resolved lifecycle is a plumbing diagnostic, not statistical proof of profitability.

## Failure and rollback procedure

Notify immediately on unknown/unprotected exposure, wrong direction/profile, reconciliation failure, causal-source violation or rejected protection. Apply existing fail-closed execution behavior and retain verified venue-native protection. Stopping a process does not prove the account flat. Any discretionary close or manual override needs its own operator authority unless covered by an explicit active instruction.

For source rollback, obtain or use the operator-approved containment scope, drain the exact current run, verify every affected symbol flat and order-free, stop only owned processes, preserve all ledgers and control files, and create/verify the immutable drain archive. Restore the preserved source into a separate checkout for inspection; do not overwrite live state or use destructive Git commands. Reconcile without placement. Re-arming prior V86 or another profile requires explicit approval and a new validated prestart boundary. Several losing trades alone do not trigger automatic strategy rejection or rollback.
