# V88 approved software deployment — live start remains operator-owned

The operator replied `approved` on September 6, 2026. The receipt was recorded at
`2026-09-06T13:51:17.495176+00:00`; this is the recording time, not a separately
verified message timestamp. The [approval document](../live-approvals/v86-to-v88-four-core-evidence-pending-20260905-v1.json)
passes the existing profile-change validator. Its historical filename contains
`pending`, but its content is `approved_for_live_transition`.

The original workspace `/Users/gestas/Prototypes/hypervector` now contains approved
source `67c6c406f6f353ead7e8617324b2915681a94c0d`, deployed by fast-forward. The
previous original commit `4fae13cf0dd878839aadf62cf683ace3e004871b` is preserved at
`backup/pre-v88-original-20260906`. The isolated review tree remains at the approved
commit. Follow-up changes contain approval, monitoring metadata, this handoff,
journal evidence, and a test that now validates a recorded approval instead of
requiring its absence. Runtime source and the approved trading TOML are unchanged.

**No live backend was started and no execution client was constructed by this
deployment procedure.** The agent cannot activate real-money trading. The operator
can use the launch command below. Approval has been received; another approval
request is not outstanding.

The [frozen proposal](2026-09-05-v88-live-proposal.md) and
[original transition guide](../guides/cohort-live-transition-and-rollback-v88.md)
remain unchanged because the approval binds their hashes. Their pending-status
language describes package preparation on September 5. This handoff records the
subsequent approval and software deployment.

## Scope and evidence

The approved profile retains BTC long, ETH long, SOL short, and HYPE long at their
existing strategy, leverage, sizing, and protection settings. It allows four
positions, one per asset, on mainnet with isolated margin. No new assets, doubled
sizing, ML activation, or automatic strategy changes were added.

The fresh unsigned venue preflight at `2026-09-06T13:51:17.520908Z` found all
retained and retiring assets flat and order-free, reconciled ledgers, four
configured positions, valid sizing, and no transition blockers. Account equity
was $4,857.58724349 at that snapshot. This observation expires as venue state
changes; the launcher's fresh checks remain necessary.

The preparation-only prestart backup completed at:
`data/backups/bidirectional_cohort/prestart_20260906T135350.777160Z_06e90a0c59b4`.
Its manifest SHA-256 is
`81783f4bde04be9c560a2a30895ec2423ee8cedae49f56b0615402d3a9d48b61`.
It includes 1,860 implementation files and passed approval and completed-transition
validation. This bundle is preparation evidence; an actual live launch creates its
own fresh bundle. No STOP/control file was present or removed during deployment.
The prior source archive and flat transition archive remain preserved as described
in the frozen guide.

The deployed unsigned observer completed eight polls with zero strategy intents;
its audit reports technical completion. This does not demonstrate live fills,
protective orders, exit handling, or profitability. Release build, deployed Python
and Rust test outcomes, CLI status, source identity, and immutable evidence hashes
are recorded in
`data/logs/research/bidirectional_cohort/overhaul_v88_approved_deployment_acceptance_20260906_v1.json`.
Initial test-environment failures are retained alongside the corrected results:
the full suite requires the locked optional test/ML dependencies. Installing those
dependencies does not activate ML in V88.

Completed verification: Python 7,998 passed, four network tests deselected,
27 warnings, 418.27 seconds; Rust 495 passed and 22 ignored. Release build and CLI
status exited successfully. The changed approval test passed all three focused
cases; Ruff and whitespace checks passed. Ignored and excluded tests are outside
these results.

The approved monitoring variant is
`configs/research/cohort_improvement_decision_overrides_v88_approved_20260906.json`.
Its five evidence files validate, and its routes and active hypotheses equal the
frozen pending variant. `approved_not_deployed` refers to live strategy activation;
software deployment is complete. The monitoring process has not started because
there is no new V88 live checkpoint to bind it to.

## Operator launch

Run from the original workspace:

```bash
cd /Users/gestas/Prototypes/hypervector
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --config configs/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --mode live --enabled --i-accept-live-risk
```

The supervised TUI owns its backend; quitting it stops that backend. Process exit
alone does not establish a flat venue account. Preserve its actual run ID,
checkpoint, logs, and fresh backup manifest for post-start acceptance.

After a fresh matching V88 live checkpoint exists, the read-only improvement loop
can run in a separate terminal:

```bash
cd /Users/gestas/Prototypes/hypervector
uv run python scripts/cohort_improvement_monitor.py \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --decision-overrides configs/research/cohort_improvement_decision_overrides_v88_approved_20260906.json \
  --out data/runtime/bidirectional_cohort/latest_v88_improvement_digest.json \
  --history data/live/research/v88_continuous_improvement.jsonl \
  --interval-seconds 120
```

Stop this loop when its backend stops. An old checkpoint or unsigned observer is
not evidence of a new live deployment. Sidecars have no order, sizing, or promotion
authority.

## Remaining acceptance and recovery

High confidence in the recorded software identity and completed technical checks,
based on the referenced local artifacts. A hash mismatch, failed fresh preflight,
or inconsistent deployed behavior would invalidate that assessment. Confidence in
future economics remains limited by conditional retrospective selection, source
gaps, and unobserved private execution paths described in the frozen proposal.

After operator startup, verify matching run/profile/source identity, all four
provider rows, source freshness, reconciliation, and all nine TUI screens against
the actual live checkpoint. The highest-value next investigation remains HYPE's
native entry, protection, hold, and exit fidelity. Bind that investigation to the
actual run and cutoff before evaluating outcomes; none is invented here.

Reconcile first attributable lifecycle events against decisions, entry age,
rounding, partial fills, protection acknowledgement, exits, fees, and funding.
Wrong direction/profile, unknown exposure, rejected protection, causal-source
violations, or unreconciled costs update the diagnosis immediately. Several losses
alone do not establish a defect or trigger an implicit economic rejection gate.

Use the preserved-source and flat-boundary recovery procedure in the frozen guide;
do not overwrite ledgers or restore an old checkout over active state. The simpler
option of leaving the backend stopped retains zero new strategy exposure but
produces no live lifecycle evidence. Operator activation enables that evidence
and the approved trading exposure. The complete live-operation objective remains
unfinished until the operator starts it and actual post-start acceptance is done.
