# Cohort v14 to v18 live transition and rollback

This runbook prepares an inactive evidence-routing experiment. It moves generic
breakout execution off BTC, ETH, and SOL; retains native HYPE breakout
execution; gives the separately developed ETH pullback provider ETH execution;
and leaves Hulk/BTC unchanged. It does not activate v18, force-close a v14
lifecycle, alter the running process, or grant execution authority.

The v18 candidate does not establish edge. Its value is cleaner causal
attribution: each executable coin has one evidence-selected provider. The ETH
pullback evidence is provisionally positive but unstable across folds, native
HYPE evidence is contradictory, and BTC Hulk evidence is contradictory.
Confidence is high in the mechanical scope difference and low-to-medium in the
economic hypothesis. Reconciled prospective fills, costs, missed opportunities,
and adverse paths would update that assessment.

## Frozen identities

- current profile: `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`
- current fingerprint:
  `e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900`
- candidate profile: `multi_asset_bidirectional_evidence_routed_candidate_v18`
- candidate fingerprint:
  `3dcf69329639bc10eaa8d20561c391419494d37e7686370bf3ea0cab29b1f158`
- HYPE provider source SHA-256:
  `3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d`
- ETH provider source SHA-256:
  `11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml",
  "current_profile_id": "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14",
  "current_profile_fingerprint": "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900",
  "current_file_sha256": "f6098f1f553a81b6731eb5d5e0897c96b7da8c3bc25295a276d9cbed44c2e007",
  "candidate_path": "configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_routed_candidate_v18",
  "candidate_profile_fingerprint": "3dcf69329639bc10eaa8d20561c391419494d37e7686370bf3ea0cab29b1f158",
  "candidate_file_sha256": "0f08062468c4b6e358cc60b3cf0b6f52aae00a46449b3f27f17b254e5f26f70e",
  "hype_source_sha256": "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d",
  "eth_source_sha256": "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|HYPE"
  ],
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed byte, fingerprint, source hash, or execution route invalidates this
contract. Regenerate and review it rather than substituting another profile.

## Current verified v14 baseline

The current live generation reported this independently created pre-start
bundle at the time this runbook was written:

```text
bundle: data/backups/bidirectional_cohort/prestart_20260806T150859.765943Z_e27a8cb63b17
manifest SHA-256: d7741273b8cbc9ce1b2bf86d4178d571b85b4f324147e45b3d5b3af52dfbb653
implementation files: 1195
implementation SHA-256: c8e7388352af7888b3d83562c0628ed25008850f29ed10f4c34e1988f525ea1c
```

This identifies the running implementation; it does not prove profitability.
A later v18 start must generate and verify a new pre-start bundle.

## 1. Verify current v14 ownership

Require a fresh checkpoint, exact v14 identity, zero faults, and observed venue
portfolio:

```bash
jq -e '
  (.status == null) and
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14" and
  .audit.run.profile_fingerprint ==
    "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900" and
  .configuration_generation.matches_runtime == true and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Exit zero proves only that checkpoint. A stale file, fault, identity mismatch,
or venue failure stops the procedure.

## 2. Request a v14 transition drain

This is a future live control action and requires explicit operator approval.
On TUI screen 7, select `TRANSITION DRAIN`, review the exact run/profile binding,
press Enter, and confirm only when authorized. Do not force-close the current
HYPE lifecycle. The drain withholds new entries while v14 continues managing
normal exits, timers, funding, and its venue-native stop.

If v14 is interrupted during an active drain, resume only the exact v14 profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml
```

Do not send SIGKILL. A different generation must not adopt an active drain.

## 3. Prove flat, order-free completion

Wait until the backend-authored checkpoint satisfies every condition:

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

Stop the owning TUI only after that predicate succeeds. Confirm no live backend
or checkpoint writer remains before archival:

```bash
pgrep -af 'scripts/multi_asset_bidirectional_live.py'
pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'
```

Both commands must return no matching process. Preview and then confirm a
recoverable archive using the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

Do not remove the transition marker manually. The archiver must retain the
drain record and refuse an incomplete or still-owned lifecycle.

## 4. Reconcile the inactive candidate at the stopped boundary

With no live backend and no rolling checkpoint writer, publish one report-only
v18 checkpoint. ETH forward evidence is included because v18 routes the exact
ETH pullback provider:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --eligible-policy-forward --once
```

Require exact v18 identity, observed venue state, and no exposure or orders:

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
    "3dcf69329639bc10eaa8d20561c391419494d37e7686370bf3ea0cab29b1f158" and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Any exposure, order, fault, or identity mismatch stops the cutover. Resume v14
to reconcile legacy exposure; do not start v18 over it.

## 5. Start v18 only after a new explicit authorization

The candidate remains inactive until the operator explicitly approves this
generation at the verified-flat boundary. The exact unified live command is:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml \
  --enabled --i-accept-live-risk
```

The launcher must acquire singleton account ownership, reconcile the venue,
and create a new hash-verified pre-start bundle before constructing live
clients. Independently verify the exact emitted bundle:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

The verifier must report `verified`, the v18 profile, nonzero implementation
file count, and nonempty manifest and implementation hashes.

After v18 is running, an additional display can attach without execution
authority or backend ownership:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml
```

## 6. Runtime acceptance

Before calling the v18 deployment mechanically correct, require:

- exact v18 profile and fingerprint in both ledger and checkpoint;
- `running_consistent`, zero faults, and fresh venue reconciliation;
- Hulk/BTC, ETH-pullback/ETH, and breakout/HYPE as the only executable routes;
- $25 maximum BTC notional, $25 maximum ETH notional, and
  $75 maximum HYPE notional, all at isolated 5x;
- both ETH directions, taker IOC entry, 60-bps protective stop, no fixed target,
  and a 12-hour fixed maximum hold;
- both HYPE directions, taker IOC entry, 80-bps protective stop, no fixed
  target, an eight-hour soft deadline while regime support is evaluated, and
  an unconditional 24-hour hard deadline;
- maximum four simultaneous positions and one position per coin;
- SOL remains observe-only for every provider;
- every first entry has one causal decision, one attributed venue fill, signed
  size agreement, a nonzero reduce-only stop OID, isolated leverage,
  liquidation telemetry, fees, funding, acknowledgement latency, and slippage;
- no inherited exposure, duplicate same-coin position, stale intent, or route
  outside the frozen execution scope.

The TUI, checkpoint, journal, and DuckDB research store must retain exact
long/short attribution, entry and exit contexts, costs, adverse/favorable
excursions, timer/stop/opposite-intent exits, and eligible missed opportunities.
No economic result automatically changes live authority. Performance remains a
reported trial outcome, not an implicit gate.

## Rollback

There is no hot rollback. Every open v18 lifecycle remains managed by its
recorded v18 contract. At the next verified flat/no-owned-order boundary,
request and complete a v18 transition drain, archive it, then launch the exact
v14 config with both explicit live-risk flags and a new verified pre-start
bundle.

Never overwrite newer ledger bytes with an older backup. Rollback changes the
executable generation; it does not erase v18 fills, journals, checkpoints,
research records, or backups.

## Failure modes and falsifiers

This procedure is invalidated by changed config or source hashes, mismatched
profile fingerprints, an incomplete drain, any venue exposure or owned order,
concurrent writers, a missing backup identity, duplicated coin exposure, or a
first-entry protection mismatch.

The economic hypothesis is weakened by after-cost losses, persistent side or
asset concentration, friction erasing gross returns, or missed-opportunity
analysis favoring a removed v14 route. It is strengthened only provisionally by
prospective reconciled outcomes with complete opportunity accounting. Neither
result mutates the live profile automatically.
