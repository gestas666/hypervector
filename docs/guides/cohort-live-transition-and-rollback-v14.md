# Cohort v11 to v14 live transition and rollback

This runbook grants the unchanged canonical breakout provider live-research
authority on BTC, ETH, SOL, and HYPE only after the currently armed v11 cohort
has drained and authenticated venue telemetry proves every coin flat and free
of owned orders. It does not force-close the current HYPE lifecycle, hot-mutate
the running process, infer venue state from the TUI, or make historical
performance an implicit execution gate.

The candidate does not establish edge. Current forward evidence proves that
the provider generated one eligible observer event on each of BTC, ETH, and
SOL during the v11 run, but one event per asset cannot estimate expectancy.
Prior historical transfer evidence was negative for ETH and SOL in both tested
blocks, while BTC was unstable and recently short-led. The operator has
explicitly authorized these routes as a live-research trial; that authorization
does not convert the evidence into a profit claim.

Confidence is high that the candidate changes only execution authority for the
existing provider and preserves the shared-account safety contract. Confidence
in cross-asset economic performance is low. Reconciled live fills, after-cost
outcomes, and missed-opportunity accounting will update that assessment.

## Frozen transition identities

- current path:
  `configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml`
- current profile:
  `multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11`
- current fingerprint:
  `9f0f53d5c3c75bcec36a8b29c75d93146d686dbd46e90d25ef5ef400b8df685c`
- current file SHA-256:
  `2a118e64ee0254134809acdf07b13c1bf581bd77f56a73097367e9f4d637c70e`
- candidate path:
  `configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml`
- candidate profile:
  `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`
- candidate fingerprint:
  `e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900`
- candidate file SHA-256:
  `f6098f1f553a81b6731eb5d5e0897c96b7da8c3bc25295a276d9cbed44c2e007`
- unchanged breakout source SHA-256:
  `3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml",
  "current_profile_id": "multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11",
  "current_profile_fingerprint": "9f0f53d5c3c75bcec36a8b29c75d93146d686dbd46e90d25ef5ef400b8df685c",
  "current_file_sha256": "2a118e64ee0254134809acdf07b13c1bf581bd77f56a73097367e9f4d637c70e",
  "candidate_path": "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml",
  "candidate_profile_id": "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14",
  "candidate_profile_fingerprint": "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900",
  "candidate_file_sha256": "f6098f1f553a81b6731eb5d5e0897c96b7da8c3bc25295a276d9cbed44c2e007",
  "breakout_source_sha256": "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hype_breakout_onset_bidirectional_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|SOL",
    "hype_breakout_onset_bidirectional_v1|HYPE"
  ],
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any byte, fingerprint, source, profile, or execution-scope mismatch invalidates
the cutover. Regenerate and review this contract instead of substituting a
nearby candidate.

## Verified implementation baselines

The running v11 generation was created from this verified pre-start bundle:

```text
data/backups/bidirectional_cohort/prestart_20260806T003309.611169Z_9f0f53d5c3c7
implementation files: 1170
implementation SHA-256: e71e4089ca2ec0acc88cd16e260e815d89dc1e52937655af45555f50bfebb882
manifest SHA-256: 6118387d217d2befb8c9670778f2492393e310e36ef5a9751569cfd470a5cfc3
```

The inactive v14 implementation was captured without credentials or execution
authority in this independently verified baseline:

```text
data/backups/bidirectional_cohort/prestart_20260806T104129.213461Z_e27a8cb63b17
implementation files: 1188
implementation SHA-256: f2e9227b94dd31e67c95eff115d42b67a1d713ceed8c03095d69df98c91fb990
manifest SHA-256: 4235c31848fa0127de377549979d756f98c28255a8576bcbb9d20961938fcc0c
execution authority: none
```

This candidate baseline proves staged source bytes only. It does not replace
the fresh mandatory pre-start bundle generated during a later live startup.

## 1. Confirm the running v11 identity

Require a fresh venue-backed checkpoint and exact current generation:

```bash
jq -e '
  (.status == null) and
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11" and
  .audit.run.profile_fingerprint ==
    "9f0f53d5c3c75bcec36a8b29c75d93146d686dbd46e90d25ef5ef400b8df685c" and
  .configuration_generation.matches_runtime == true and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Exit code zero and JSON `true` prove only that snapshot. A stale checkpoint,
fault, identity mismatch, or venue-valuation failure must be resolved before a
drain request.

## 2. Request the identity-bound transition drain

This is a live control-plane action. On TUI screen 7, select
`TRANSITION DRAIN`, press Enter, verify the exact `MULTI` scope, and press `y`
only under current operator authorization. The accepted request must bind the
current run ID, v11 profile, and v11 fingerprint.

The drain withholds new openings while normal strategy exits, timer exits,
manual closes, and venue-native protection continue. It does not close the
current HYPE position, start v14, or alter a strategy parameter.

### Optional pending-v14 TUI projection during the drain

At most one process may write
`data/runtime/bidirectional_cohort/latest_checkpoint.json`. After stopping an
existing standalone checkpoint writer, a report-only sidecar may compare the
still-running v11 ledger with the exact v14 candidate:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio
```

During the open HYPE lifecycle, require `matches_runtime=false`,
`restart_state=wait_for_flat_and_no_orders`, `blocking_assets=["HYPE"]`, and
`execution_authority=none`. This only makes the pending generation visible in
the TUI; it does not stage, activate, or restart v14.

Do not add `--eligible-policy-forward` to this mixed-generation checkpoint.
That ETH observer is deliberately bound to the v11 source fingerprint and
must fail if labeled with v14. Resolve or publish it separately under the v11
identity. Stop the candidate-bound checkpoint writer before drain archival.

If the backend is interrupted while the drain is active, resume only v11:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml
```

Do not send SIGKILL. A different profile must not adopt an active drain.

## 3. Prove completion and archive the drain

Wait for the backend-authored checkpoint to satisfy every predicate:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    (.final_state == "FLAT" or .final_state == "STOPPED") and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .transition_drain.status == "completed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Require no live backend or checkpoint writer before archival:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live.py'
pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'
```

Both commands must return no matching process. Preview and then confirm the
recoverable archive with the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

The archiver refuses runtime ownership, incomplete state, identity mismatch,
and archive collision. Do not remove the transition marker manually.

## 4. Reconcile stopped venue state against v14

With no backend or rolling checkpoint writer, publish one report-only
candidate-bound checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml \
  --venue-portfolio --once
```

Require the exact candidate identity and flat venue boundary:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    (.final_state == "FLAT" or .final_state == "STOPPED") and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .configuration_generation.restart_state == "candidate_flat_no_orders" and
  .configuration_generation.current_profile_fingerprint ==
    "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900" and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Any new position, order, fault, or identity mismatch stops the transition. If
legacy exposure reappears, resume v11 and reconcile it; do not start v14 over
that exposure.

## 5. Start v14 through the unified launcher

The candidate remains inactive until this exact command is deliberately run
with live authority at the verified-flat boundary:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml \
  --enabled --i-accept-live-risk
```

The backend must acquire singleton account ownership, reconcile the venue, and
create and hash-verify a fresh pre-start bundle before it constructs execution
authority. Independently verify the exact emitted bundle:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

Require `status=verified`, previous profile v11, target profile v14, nonzero
implementation file count, and nonempty manifest and implementation hashes.

## 6. Accept the v14 runtime and first lifecycles

Before treating v14 as correctly deployed, require:

- exact v14 profile and fingerprint in backend and checkpoint telemetry;
- `running_consistent`, zero faults, and venue-backed reconciliation;
- exactly Hulk/BTC and breakout/BTC, breakout/ETH, breakout/SOL, breakout/HYPE
  executable, with every other provider-symbol mapping report-only;
- both long and short enabled on all four breakout routes;
- isolated 5x with $25 BTC maximum notional, $25 ETH maximum notional,
  $75 SOL maximum notional, and $75 HYPE maximum notional;
- the unchanged breakout contract: taker IOC entry, 80-bps protective stop,
  no fixed target, fresh-opposite-intent close, regime-aware eight-hour soft
  deadline, and unconditional 24-hour hard deadline;
- maximum four simultaneous positions and one position per coin;
- unchanged HYPE provider source hash and unchanged HYPE v1 behavior;
- no position or owned order inherited across the flat boundary;
- checkpoint backup identity matching the independently verified startup bundle.

For every asset's first breakout entry, require one causal provider decision,
one attributed venue fill, signed-size agreement, a nonzero reduce-only stop
OID, isolated leverage, liquidation telemetry, fees, funding, acknowledgement
latency, and slippage. The exact stop must remain reconciled on every open
checkpoint. Missing protection, duplicate same-coin exposure, stale intent,
or a route outside the frozen execution scope is a technical failure.

The first economic review occurs after at least 20 resolved lifecycles per
provider-symbol route or 30 calendar days, whichever comes later. That is an
analysis checkpoint, not proof of edge and not an automatic performance gate.
The journal must retain wins, losses, fees, funding, slippage, stop/timer/
opposite-intent exits, long/short attribution, regime and order-book context,
and eligible missed opportunities.

## Rollback

There is no hot rollback. Continue managing every open v14 lifecycle under its
recorded contract. At the next verified flat/no-owned-order boundary, request
and complete a v14 transition drain, preserve and archive its evidence, then
launch the exact v11 path with explicit live authority and a newly verified
pre-start backup.

Never restore older ledger bytes over newer venue-reconciled state. Rollback
changes the executable generation; it does not erase v14 fills, journals,
backups, checkpoints, or research evidence.

## Falsifiers and update evidence

This runbook is invalidated by changed config/source bytes or fingerprints, a
different execution map, incomplete drain, open venue exposure, owned orders,
faults, concurrent checkpoint writers, missing backup identity, duplicate
same-coin exposure, or first-entry protection disagreement.

The economic hypothesis is weakened by after-cost profit factor at or below
one, persistent loss on either side, venue friction erasing gross return, or
repeated adverse selection around the 80-bps stop. It is strengthened only
provisionally by reconciled prospective results with complete opportunity
accounting and stable long/short attribution. Neither outcome changes live
authority automatically.
