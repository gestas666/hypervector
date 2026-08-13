# Cohort v11 to v12 live transition and rollback

This runbook adds the bounded ETH breakout-transfer canary only after the
currently armed v11 cohort has drained naturally and authenticated venue
telemetry proves every coin flat and free of owned orders. It does not force an
exit, hot-mutate a running strategy, infer venue state from the TUI, or use
research performance as a technical startup gate.

The ETH hypothesis is low confidence and does not establish edge. Its purpose
is to gather reconciled fills, friction, path, and missed-opportunity evidence
under a deliberately small live allocation.

The exact-cap shared-account replay completed on 2026-08-06 does not qualify
the combined v12 composition as a historically profitable portfolio. On one
`$500` account at the configured caps, development produced `-$59.64` with PF
`0.882` over `1,329` trades; the already-opened final 60-day block produced
`-$5.01` with PF `0.954` over `273` trades. ETH alone remained positive in both
blocks (`+$3.97`/PF `1.115`, then `+$0.80`/PF `1.120`). BTC Hulk and HYPE remain
contradictory, and HYPE supplied most of the historical loss. Therefore a v12
launch, if freshly authorized, is a bounded live research deployment—not an
economic promotion or claim of expected profitability. Source:
`data/logs/research/current_cohort_shared_portfolio_v11_eth12_v2_20260806.json`.
Confidence is medium because the samples are large but the final block was
already opened and bar replay cannot reproduce private queue position. Fresh
venue-executed portfolio evidence or an authenticated event-level replay that
materially changes the result would update this assessment.

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
  `configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml`
- candidate profile:
  `multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12`
- candidate fingerprint:
  `0f2c2e8ed152c060697685546e839d98c953e8aeb324ec00328a8f41e72a217e`
- candidate file SHA-256:
  `b6551b4a4188a64098e70a92f5abbb828d5a308b94f154938c5d709f78e0f386`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml",
  "current_profile_id": "multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11",
  "current_profile_fingerprint": "9f0f53d5c3c75bcec36a8b29c75d93146d686dbd46e90d25ef5ef400b8df685c",
  "current_file_sha256": "2a118e64ee0254134809acdf07b13c1bf581bd77f56a73097367e9f4d637c70e",
  "candidate_path": "configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12",
  "candidate_profile_fingerprint": "0f2c2e8ed152c060697685546e839d98c953e8aeb324ec00328a8f41e72a217e",
  "candidate_file_sha256": "b6551b4a4188a64098e70a92f5abbb828d5a308b94f154938c5d709f78e0f386",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hype_breakout_onset_bidirectional_v1|HYPE",
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH"
  ],
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any byte, fingerprint, profile, or execution-scope mismatch invalidates the
cutover. Regenerate and review the contract instead of substituting a nearby
candidate.

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

Exit code zero and JSON `true` prove only the current snapshot. Any unavailable
checkpoint, fault, stale identity, or venue valuation failure must be resolved
before requesting the drain.

## 2. Request the identity-bound transition drain

This is a live control-plane action and requires current explicit operator
authorization. In the TUI, open screen 7, select `TRANSITION DRAIN`, press
Enter, review the exact `MULTI` scope, then press `y` to confirm. The backend
must record the accepted request under the current run and profile.

After acceptance, new openings are withheld while normal strategy exits,
manual closes, timer exits, and venue protection continue. The request does not
close the current HYPE trade, start v12, or alter any strategy parameter.

If the backend is interrupted while the drain is active, resume only the exact
v11 identity:

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

If a TUI supervised v11, quit that TUI only after completion so its launcher
can reap the stopped backend and checkpoint sidecar. Require no remaining live
backend or checkpoint writer before archival:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live.py'
pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'
```

Both commands must return no matching process. Preview and then explicitly
confirm the recoverable archive with the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

The command refuses active runtime ownership, incomplete or mismatched state,
and archive collisions. Do not remove the transition file manually.

## 4. Reconcile the stopped venue state against v12

With no backend or rolling checkpoint writer, publish one report-only
candidate-bound checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml \
  --venue-portfolio --once
```

Require the exact target identity and the venue-backed flat boundary:

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
    "0f2c2e8ed152c060697685546e839d98c953e8aeb324ec00328a8f41e72a217e" and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Any new position, order, fault, or identity mismatch stops the transition. If
legacy exposure reappears, resume the exact v11 generation and reconcile that
lifecycle; do not start v12 over it.

## 5. Start v12 through the unified launcher

This is the only v12 live-arm command in this runbook. It requires fresh
explicit live-risk authorization at execution time:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml \
  --enabled --i-accept-live-risk
```

The backend must acquire singleton account ownership, reconcile the venue, and
create and hash-verify a fresh immutable pre-start bundle before constructing
execution authority. Require the `pre-start backup verified` log line and
independently verify the exact emitted bundle:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

The verifier must report `status=verified`, previous profile v11, target profile
v12, a nonzero implementation file count, and nonempty manifest and composite
implementation hashes.

## 6. Accept the v12 runtime and first ETH lifecycle

Before treating the new generation as correctly deployed, require:

- exact v12 profile and fingerprint in backend and checkpoint telemetry;
- `running_consistent`, zero faults, authenticated venue reconciliation;
- exactly Hulk/BTC, HYPE-breakout/HYPE, and ETH-transfer/ETH executable;
- all remaining provider-symbol pairs explicitly report-only;
- both ETH directions enabled, with $25 maximum ETH notional, isolated 5x,
  60-bps protective stop, and 12-hour fixed maximum hold;
- maximum four simultaneous positions and one position per coin;
- unchanged BTC and HYPE execution, sizing, and exit contracts;
- TUI screen 2 labels ETH entry filters as automatic execution inputs rather
  than report-only annotations;
- no position or owned order inherited across the verified-flat boundary;
- checkpoint backup identity matches the independently verified bundle.

For the first ETH entry, require one exact provider decision and one venue fill,
signed size agreement, nonzero protective-stop OID, isolated leverage,
liquidation telemetry, fees, funding, acknowledgement latency, and slippage.
The stop identity must remain reconciled on every open checkpoint. Missing
protection, a duplicate ETH position, stale intent admission, or an unexpected
symbol route is a technical fault and invalidates implementation parity.

Twenty resolved ETH lifecycles is the first economic review checkpoint. It is
not proof of edge and it is not an implicit automatic performance gate. The
journal must retain wins, losses, fees, funding, slippage, hold/stop exits,
long/short attribution, regime context, order-book context, and eligible missed
opportunities.

## Rollback

There is no hot rollback. Continue managing any open v12 lifecycle under its
recorded provider contract. At the next verified flat/no-owned-order boundary,
request and complete a v12 transition drain, preserve and archive its evidence,
then launch the exact v11 path with fresh explicit live authority and another
verified pre-start backup.

Never restore older ledger bytes over newer venue-reconciled state. A rollback
changes the executable generation; it does not erase v12 fills, journals,
backups, checkpoints, or research evidence.

## Falsifiers and update evidence

The runbook is invalidated by changed config bytes or fingerprints, a wider or
different execution map, incomplete drain, open venue exposure, owned orders,
faults, concurrent checkpoint writers, missing backup identity, or first-ETH
protection disagreement.

The economic hypothesis is weakened by after-cost PF at or below one,
persistent loss on both ETH sides, live friction erasing the historical surplus,
or repeated adverse selection around stops. It is strengthened only
provisionally by reconciled prospective outcomes with stable side attribution
and complete opportunity accounting. Neither result changes live authority
automatically.
