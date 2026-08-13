# Cohort v10 live transition and rollback

This runbook changes the shared Hyperliquid cohort only after a venue-backed
checkpoint proves every position and owned order flat. It does not close a
position to manufacture that boundary, hot-mutate a running strategy, or treat
research performance as a technical startup gate.

## Frozen identities

- current legacy profile: `configs/multi_asset_bidirectional_canary.toml`
- current legacy fingerprint:
  `c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b`
- selected inactive candidate:
  `configs/multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml`
- candidate profile:
  `multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10`
- candidate fingerprint:
  `a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08`
- candidate file SHA-256:
  `aa5bf4d1b3261c7ff7defe5cf1fe6701ecac39052579553eeb53419dfbbf1197`
- preserved rollback candidate:
  `configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml`

The selected candidate can execute only Hulk/BTC and canonical
HYPE-breakout/HYPE. It additionally evaluates HYPE-breakout on BTC, ETH, and
SOL as report-only mappings so the shared ledger, checkpoint, and TUI expose the
cross-asset transfer experiment without a second venue-fetch process. HYPE
remains $75 maximum notional, isolated 5x, with the existing eight-hour soft
boundary and regime-supported extension to a 24-hour hard maximum.

<!-- cohort-transition-contract:start -->
```json
{
  "candidate_path": "configs/multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10",
  "candidate_profile_fingerprint": "a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08",
  "candidate_file_sha256": "aa5bf4d1b3261c7ff7defe5cf1fe6701ecac39052579553eeb53419dfbbf1197",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hype_breakout_onset_bidirectional_v1|HYPE"
  ],
  "hype_breakout_observation_scope": ["BTC", "ETH", "SOL", "HYPE"],
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any identity mismatch stops the transition. Do not substitute v9, a
fixed-eight-hour profile, the standalone observer, or a staged TUI draft.

## Current-process limitation

The currently armed process predates transition-drain support and honestly
reports `transition_drain.status == "unavailable"`. It cannot be upgraded in
memory. Do not stop or restart it while a position is open merely to load v10.
Its one-time cutover therefore retains an entry race between observing a flat
checkpoint and processing the STOP request. If a new lifecycle appears during
that interval, abort the transition and continue managing it under the legacy
contract.

## 1. Prove the legacy flat boundary

Wait for the continuously published venue-backed checkpoint, then run:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    (.final_state == "FLAT" or .final_state == "STOPPED") and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .transition_drain.status == "unavailable"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

After the legacy process has stopped normally, a terminal asset may report
`STOPPED` instead of `FLAT`. Both states are accepted here only with exact zero
signed size and zero owned order IDs. The new backend independently reconciles
the authenticated venue position and open-order set before allowing any
strategy action; any unexplained exposure or order refuses startup.

Only exit code zero and JSON `true` establish this provisional boundary. Any
open position, owned order, fault, stale checkpoint, or unavailable venue
portfolio blocks the cutover.

Immediately request the exact legacy STOP path:

```bash
touch data/live/bidirectional_cohort/STOP
```

Do not send SIGKILL. After normal shutdown, both checks must return no process:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live.py'
pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'
```

Quit any monitor TUI before publishing a manual checkpoint so two writers do
not race on `latest_checkpoint.json`.

## 2. Reconcile the stopped venue state against v10

Publish one report-only candidate-bound checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Then require both the venue boundary and exact candidate identity:

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
    "a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

If a position or order appeared, restart only the exact legacy profile and
reconcile that lifecycle. Do not start v10.

When all predicates pass and no backend or checkpoint writer exists, preserve
the ephemeral STOP request rather than deleting it. Replace `<UTC>` with a
unique inspected timestamp:

```bash
mv data/live/bidirectional_cohort/STOP \
  data/backups/bidirectional_cohort/legacy_STOP_<UTC>
```

Refuse the move if the destination already exists. Do not move or remove any
ledger, checkpoint, operator command, or backup bundle.

## 3. Start v10 through the unified launcher

This is the only live-arm command in this runbook. It still requires fresh,
explicit operator authorization at execution time:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml \
  --enabled --i-accept-live-risk
```

The backend must acquire the singleton account lock and create, restore, and
hash-verify a fresh immutable pre-start bundle before constructing an
authenticated Hyperliquid adapter. Startup refuses a missing or empty bounded
implementation source set.

Require a backend log line containing `pre-start backup verified`. Copy the
exact printed bundle path and independently verify it:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

The verifier must report `status=verified`, previous profile
`multi_asset_bidirectional_canary_v2`, target profile
`multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10`, a
nonzero implementation file count, and a nonempty composite implementation
SHA-256. A missing implementation identity is a refusal, not a warning.

## 4. Accept the new runtime identity

Before accepting the run as correctly configured, require:

- runtime profile and full fingerprint exactly match v10;
- lifecycle is `running_consistent` with zero faults;
- Hulk/BTC and HYPE-breakout/HYPE are the only executable mappings;
- HYPE-breakout/BTC, ETH, and SOL labeled observe-only;
- HYPE-breakout/HYPE labeled bidirectional canary;
- all Range Onset mappings, Source Follow/BTC, and Hulk/ETH, SOL, and HYPE are
  observe-only;
- HYPE maximum notional is $75 at isolated 5x;
- HYPE retains the eight-hour soft and 24-hour hard extension contract;
- all four HYPE-breakout evaluations appear in backend telemetry;
- no prior position or owned order was inherited from the flat legacy run;
- the `configuration_identity.prestart_backup` object matches the independently
  verified bundle, manifest hash, implementation count, and source hash.

The existing TUI must display the unified transfer rows through backend data.
It must not fetch market data, derive signals, or infer missing research state.
No automatic strategy promotion, sizing, filtering, or execution authority may
come from the observer rows.

On the first position, require matching signed venue size, nonzero protective
stop OID, isolated leverage, liquidation price, provider identity, entry regime,
fees, funding, acknowledgement latency, and slippage. A missing stop or venue
disagreement is a live fault.

## Future drain-capable transitions

Once v10 is running, later profile changes use its default-off transition
drain. On TUI screen 7, request `TRANSITION DRAIN` only with current explicit
operator authorization. The backend withholds new openings, preserves venue
protection, and continues normal strategy/manual/timer exits. It stops only
after every position and owned order is absent.

Require this predicate instead of the legacy predicate:

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

If a drain-capable backend is interrupted while the marker is active, ordinary
startup stays refused. Recover only the exact active profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config <exact-active-profile>
```

After a completed drain, preview and then explicitly confirm its recoverable
archive operation using the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

The archive command refuses an active backend, incomplete marker, identity
mismatch, or archive collision.

## Rollback

There is no hot rollback. Continue managing any open v10 lifecycle under its
recorded plan. At the next verified flat/no-owned-order boundary, drain and stop
v10, preserve its mandatory pre-start bundle and append-only ledger, and choose
one explicitly verified profile:

- v9 restores the same execution scope without unified transfer observation;
- `multi_asset_bidirectional_canary.toml` restores the prior wide legacy scope.

Use the same unified launcher, fresh explicit live authority, fresh pre-start
backup, and first-position protection checks. Never restore archived bytes over
newer venue-reconciled state.

## Evidence that updates or invalidates this runbook

The transition is invalidated by a changed v10 file or fingerprint, an open
venue position or owned order at the boundary, any fault, concurrent checkpoint
writers, missing fresh backup identity, unexpected execution mapping, missing
four-asset observer coverage, or first-position protection disagreement.

Economic selection remains provisional. Reconciled after-cost closes, side
coverage, outcome concentration, missed opportunities, observer paths, realized
friction, rate-limit behavior, and regime/order-book context update the next
revision. Poor performance is reported evidence, not an implicit technical
abort condition.
