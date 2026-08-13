# Inactive v25-to-v31 transition and rollback contract

This guide prepares the minimal HIP-3 Swing-pruned v31 candidate without
activating or staging it. v25 remains active and owns every current lifecycle
and venue protection. This document does not authorize a restart, drain,
order, close, profile switch, or live execution.

<!-- cohort-transition-contract:start -->
```json
{
  "current_run_id": "bidirectional-live-1786182011216",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "current_file": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "candidate_profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
  "candidate_profile_fingerprint": "b8b330e0d8ee784e08236df41e2b218d2ab01ad2d6292ac6727d589ed040e91a",
  "candidate_run_fingerprint_observe": "ae562181ab6036cd702a9c2ede07e96b1143af4c8034809fc6fdbf59e7bfc23f",
  "candidate_file": "configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml",
  "candidate_file_sha256": "7a9e0f3de94a2f2c4fdd3b68c97bb60e55cba63335c5a41ef85f2e78813e8d2f",
  "execution_scope": [
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SPCX",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SP500",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hulk_expansion_bidirectional_tuned_v2|ETH",
    "hulk_expansion_bidirectional_tuned_v2|HYPE",
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    "hype_breakout_onset_bidirectional_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|HYPE",
    "hype_breakout_onset_bidirectional_v1|SOL",
    "hypervelocity_source_follow_bidirectional_5m_v1|BTC",
    "range_onset_bidirectional_v1|BTC",
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|HYPE",
    "range_onset_bidirectional_v1|SOL"
  ],
  "observe_only_scope": [
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK"
  ],
  "maximum_positions": 9,
  "one_position_per_asset": true,
  "research_revision_id": "ec25c0b3a4ce9fb5151a1dc0d23e88b4e917ce0c50c1664e68b79ba4c627fbf4",
  "research_record": "docs/research-journal/hip3-route-authority-pruning-v2.json",
  "research_record_sha256": "6b4205fcd5823624c23fb2d3cd52786f29c96343d80ce6e58f887d7930212d28",
  "forward_baseline": "data/logs/research/bidirectional_cohort/v31_route_forward_baseline_20260809T185635Z.json",
  "forward_baseline_sha256": "81e2b130e047f7f6a7708678eb837b2e7f7d43d6df1e6a8e9f8496fe980424e0",
  "comparison_artifact": "data/logs/research/hip3_route_authority_pruning_20260809.json",
  "comparison_artifact_sha256": "af1f452a1ab4b00379f43cef752cd85016397b975047b927eb56970fe6af4007",
  "pressure_clock_diagnostic": "data/logs/research/bidirectional_cohort/v25_hip3_pressure_clock_root_cause_20260808T193618Z.json",
  "pressure_clock_diagnostic_sha256": "aa24bb752350511f6d20ed492d1a992897a1d070abe5a4c845ed8ba8179fae78",
  "pressure_repair_observer": "data/logs/research/bidirectional_cohort/v25_pressure_parity_observer_20260808T201243Z.json",
  "pressure_repair_observer_sha256": "b72817ae403a72aa1a5649174d1a9828d8aee954bd1db9fde4013bd9bfb3b22d",
  "candidate_active": false,
  "transition_authorized": false,
  "flat_and_order_free_verified": false,
  "transition_readiness_snapshot": null,
  "prechange_bundle": null
}
```
<!-- cohort-transition-contract:end -->

## Candidate scope

V31 retains all nine assets, one position per asset, nine portfolio slots,
isolated 5x configuration, both long and short, current sizing, stops, targets,
maximum holds, strategy priorities, and all core/index routes. It changes only
commodity Swing execution authority:

- SNDK Swing becomes observation-only;
- BRENTOIL Swing becomes observation-only;
- GOLD Swing remains executable; and
- SNDK, GOLD, and BRENTOIL Breakout remain executable.

Observation-only means signals and causal markouts continue to be journaled;
it does not mean the route disappears from research.

## Why the candidate is inactive

On the common-full stress window, the exact minimal prune changed the shared
portfolio from `-$1.68`, PF `0.982` to `+$1.93`, PF `1.024`. Nominal net fell
from `+$18.09` to `+$17.23`. The candidate remained `-$12.98` after removing
its largest stressed winner, and available live evidence contains only one
SNDK Swing loss and no BRENTOIL close. Confidence is medium, not sufficient for
automatic promotion or an established-profitability claim.

## 1. Preserve active v25

Until every v25 lifecycle resolves, do not stage v31, replace the profile,
restart the backend, or adopt positions under another generation. A fresh
checkpoint must show the exact v25 profile, zero faults, and venue-native
protection for every open position.

Refresh the read-only route tracker without touching the backend:

```bash
uv run python scripts/v31_route_forward.py
```

The continuous report-only monitor also maintains the compact hash-chained
`data/logs/research/bidirectional_cohort/v31_route_material_changes.jsonl`.
It appends only material route, economic, authority, or health state changes;
checkpoint timestamps and evaluation-count-only refreshes are deduplicated.
The bounded current snapshot and raw ledgers remain the detailed evidence
sources. A corrupt journal chain is an explicit monitoring failure and must not
be replaced with an empty history.

## 2. Request a transition drain only after explicit authorization

An authorized transition drain withholds new entries on flat symbols while
preserving strategy exits, maximum-hold handling, manual closes, and existing
venue-native stops. The drain does not launch v31.

If an authorized drain is interrupted, resume only the same v25 profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml
```

## 3. Prove and archive the flat boundary

The checkpoint must report `transition_drain.status == "completed"`. It must
also prove all nine assets terminal, every signed position zero, every owned
order list empty, no health fault, and agreement between venue and ledger.

Preview the exact drain archive operation first:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786182011216
```

Only after checking the printed identity may the operator repeat that exact
command with `--yes`. The archive must verify byte identity before clearing the
live drain marker; it does not delete the v25 ledgers.

The current contract intentionally leaves `transition_readiness_snapshot` and
`prechange_bundle` null. They must be generated at the future boundary rather
than copied from prior transitions.

## 4. Create and verify fresh implementation evidence

With no live owner, create a new credential-free prechange bundle:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab
```

Then verify the exact emitted path:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-v31-path>
```

Require a nonzero implementation file count, matching implementation SHA-256,
the v31 profile fingerprint, no strategy drift, and no execution authority.
The mandatory live prestart bundle will still be created again by the armed
launcher before constructing an authenticated adapter.

## 5. Verify the candidate without live authority

Load v31 in observe mode and require all nine assets, 24 observed provider
pairs, 22 executable candidate pairs, the two exact observation-only Swing
pairs, both directions, and nine slots. No inherited position or order may be
assigned to v31.

```bash
uv run python scripts/multi_asset_bidirectional_observe.py \
  --config configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --ledger-root data/observe/v31-flat-preflight \
  --max-polls 2
```

This command is disarmed and must use the isolated observer root shown above.
It is not a live launch.

## 6. Launch template requiring renewed authority

This template is not current authorization. Run it only after the completed
drain, archive, flat venue reconciliation, fresh backups, disarmed preflight,
and another explicit operator acceptance of live risk:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml \
  --enabled --i-accept-live-risk
```

Before accepting the first new entry, verify the fresh configuration identity,
mandatory prestart bundle, profile fingerprint, 22/2 authority split, backend
heartbeat, zero faults, and flat initial venue/ledger state.

After the first completed HIP-3 breakout-pressure evaluation, verify the
staged pressure-clock repair from the new v31 ledger. Each of `xyz:SP500`,
`xyz:SPCX`, `xyz:SNDK`, `xyz:GOLD`, and `xyz:BRENTOIL` must publish finite
numeric `imbalance_10` and `pressure_age_seconds`; pressure age must be
nonnegative and no greater than the configured 30-second maximum. Bind the
evaluation to an exact-symbol authoritative book at or before its provider
cutoff, and verify that funding reconciliation has neither an overlapping nor
skipped window. A missing value despite an admissible same-cycle book is a
technical adoption failure, not an economic blocker or a reason to relax the
pressure-age rule.

The historical v25 metric gaps remain attributed to the old source-bound run;
do not relabel them as complete or splice them into the new v31 baseline. The
v31 checkpoint may claim complete provider metric telemetry only from its own
new-run evidence. If this adoption check fails, preserve any venue-native
protection, record the exact ledger/config/implementation identities, and do
not describe v31 as technically accepted.

Run the immutable, report-only verifier against the first complete v31
checkpoint:

```bash
uv run python scripts/v31_poststart_acceptance.py
```

The command writes a timestamped artifact under
`data/logs/research/bidirectional_cohort/`. A technically accepted report must
contain `"accepted": true` and exit with status 0. A structurally valid but
incomplete or unhealthy checkpoint is preserved as `"accepted": false` and
returns exit status 2. Identity or malformed-evidence errors fail explicitly.
This report cannot transition, place, close, resize, or promote anything.

The verifier proves exact candidate identity, cumulative new-run coverage,
finite per-route pressure metrics, the 30-second pressure-age bound, zero
faults, inactive drain state, and protection for every open position. It uses
the checkpoint's aggregate metrics plus the hash-bound causal-book repair; it
does not independently reconstruct raw-book selection or funding cursor
continuity. Run the second immutable verifier to close that raw-ledger boundary:

```bash
uv run python scripts/v31_raw_ledger_acceptance.py
```

This command snapshots stable prefixes of the exact v31 cohort ledger and all
nine asset ledgers. Its `causal_pressure_books` check recomputes top-ten
imbalance, requires the exact-symbol book to be the latest book available at
the common provider cutoff, and rejects a future, stale, older, or mismatched
book. Its `funding_cursor_continuity` check requires one typed funding-window
commit after each routing cycle, exact prior-end/next-start continuity, the
target provider cutoff, and transaction-identity deduplication. Both the
aggregate and raw reports must contain `"accepted": true`; either exit status
2 is a preserved technical rejection. Do not interpret technical acceptance
as proof of positive expectancy.

Refresh `scripts/v31_route_forward.py` after the first complete v31 checkpoint.
It must report `phase=candidate_v31_forward`; the two removed routes must show
`current_authority=observe_only`, and the four retained controls must show
`current_authority=executable`. That snapshot is the new forward baseline.
The material-change journal must append the v25-to-v31 identity and authority
transition while retaining the prior v25 event through its SHA-256 chain.

## Rollback

No hot rollback is permitted while v31 owns a position or protective order.
If rollback is requested:

1. activate a generation-bound v31 transition drain after explicit approval;
2. retain all venue-native protection while positions resolve;
3. prove verified flat-and-order-free venue and ledger state;
4. archive the completed v31 drain and run evidence;
5. create and independently verify a new implementation backup;
6. select the preserved target profile explicitly; and
7. require fresh `--enabled --i-accept-live-risk` authority.

Do not reuse a prior staged profile, flat checkpoint, order identity, live-risk
acceptance, or implementation hash as rollback authority.
