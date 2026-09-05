# v52 to v53 HYPE freshness transition contract

## Exact successor

The approved successor is
`multi_asset_growth_first_5000_hype_freshness_repair_v53`, fingerprint
`f6378e473088b962724176f1b4aaf0857d4e2a6c3bf0103c2d1794d6bfd46a82`.
Its config SHA-256 is
`d1f6a4e6eb77ba9d8ad1069e703e54611feeaacec6242ac0000eb6f0f0ee4f2b`.

The only strategy-contract delta from v52 is the persisted HYPE soft-hold
freshness limit:

```toml
maximum_hold_evidence_maximum_age_seconds = 60
```

BTC and HYPE assets, three provider-symbol routes, four directional scopes,
sizing, leverage, entries, protective stops, targets, opposite-signal exits,
soft deadlines, and hard deadlines otherwise remain unchanged.

## Repair semantics and validation

At the eight-hour HYPE soft deadline, extension requires both provider-native
and canonical regime evidence. Each observation must be present, non-future,
and no older than 60 seconds. Missing, partial, future, or stale evidence exits
at the soft deadline. The 24-hour hard deadline, 80-bps venue stop, and eligible
opposite-signal exit remain independent and unchanged.

The standing approval is bound by
`docs/research-journal/v51-standing-required-change-preapproval-v1.json`; the
specific report-only proposal is
`docs/research-journal/v52-hype-maximum-hold-evidence-freshness-v1.json`.
Neither artifact can place an order.

The exact v53 stress report is
`data/logs/research/bidirectional_cohort/v53_growth_sizing_stress_20260817_v1.json`.
For the two-asset $5,000 roster, the sampled p99 simultaneous stop wave is
**$92.792193**, or **1.855844%**. This is a deterministic scenario, not a
probability forecast or loss ceiling. Gaps, latency, liquidation mechanics,
and adverse selection can lose more.

The verified live-start backup is
`data/backups/bidirectional_cohort/prestart_20260817T045033.732653Z_f6378e473088`.
Its implementation SHA-256 is
`a268627a9ed4c478d8bb63a529c0da29c628376163b080bb99122ae2ac8741e5`.

## Required flat boundary

The transition requires zero venue positions and zero owned orders. V52 must
stop normally from an exact fresh flat cohort snapshot. The final checkpoint,
preflight, accounting epoch, and backup remain recoverable and profile-bound.
The first v53 cockpit must show **ALL-TIME 0/0** and **CURRENT RUN 0/0** for the
new epoch; prior history remains append-only and is not deleted.

Request the exact v52 stop only at the next verified flat snapshot:

```bash
uv run python scripts/cohort_legacy_flat_stop.py \
  --ledger data/live/bidirectional_cohort/decisions.jsonl \
  --stop-file data/live/bidirectional_cohort/STOP \
  --expected-profile-fingerprint 662d28b352cfc4f09e08c71ee67c8f044421483f2932539b09ea082b5e4f27f7 \
  --expected-run-id bidirectional-live-1786927506379 \
  --expected-symbol BTC --expected-symbol HYPE \
  --poll-seconds 0.1 --timeout-seconds 60 --write-stop
```

After backend and checkpoint-writer exit, preserve the STOP request with the
transition evidence, remove it from the active path, and confirm both runtime
locks are free before any successor launch.

The final drain-only v52 run was `bidirectional-live-1786941484060`. Its
authenticated drain request `f253351aeb5a4ae1af1353795c56fe67` completed
flat and order-free, then was archived by
`scripts/cohort_transition_drain_archive.py` at
`data/backups/bidirectional_cohort/transition_drains/transition_drain_20260817T044502Z_f253351aeb5a4ae1af1353795c56fe67.json`.

## Final preflight and accounting epoch

Generate a new post-stop preflight; the preliminary v1 snapshot cannot be used
for the accounting boundary:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --active-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v53_final_flat_preflight_20260817_v3.json
```

Require exact v53 identity, current fees/leverage/depth, technically ready,
zero venue positions, zero owned orders, and exact BTC/HYPE ledger coverage.
Dry-run, then publish the immutable v53 epoch:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --successor-config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v53_final_flat_preflight_20260817_v3.json \
  --prestart-bundle data/backups/bidirectional_cohort/prestart_20260817T044846.010340Z_f6378e473088 \
  --epoch-id v53_hype_freshness_repair_r2 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v53_hype_freshness_f6378e4_r2

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --successor-config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v53_final_flat_preflight_20260817_v3.json \
  --prestart-bundle data/backups/bidirectional_cohort/prestart_20260817T044846.010340Z_f6378e473088 \
  --epoch-id v53_hype_freshness_repair_r2 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v53_hype_freshness_f6378e4_r2 \
  --yes
```

Never reuse the v52 epoch or a v53 epoch under another fingerprint.

## Live start and poststart acceptance

Start only after the final preflight and epoch pass and the STOP path is safely
archived:

```bash
uv run python scripts/multi_asset_bidirectional_live.py \
  --config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v53_hype_freshness_f6378e4_r2 \
  --enabled --i-accept-live-risk
```

Start the exact report-only checkpoint writer for the new run. After both asset
ledgers advance, run:

```bash
uv run python scripts/v53_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v53_final_flat_preflight_20260817_v3.json
```

Acceptance must report the exact profile/fingerprint, three routes, four sides,
freshness limit 60, bound execution plans, zero identity gaps, and no inherited
v52 lifecycle.

## Final attach-only TUI

Once v53 and its checkpoint writer are verified, this command is attach-only:

```bash
cd /Users/gestas/Prototypes/hypervector && \
CARGO_TARGET_DIR=/tmp/hypervector-v53-cargo \
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v53_hype_freshness_f6378e4_r2 \
  --refresh-ms 500
```

## Rollback and falsifiers

Rollback is permitted only from a flat and order-free v53 boundary. Preserve
all v52/v53 ledgers, epochs, checkpoints, backups, and audits.

Abort or stop new entries on any identity, epoch, lock, venue, ledger, route,
or protection mismatch; any extension from missing/future/stale evidence; any
unprotected open position; any duplicate owned order; initial accounting other
than 0/0; or a failed poststart acceptance. Strategy profitability remains an
empirical forward result, not a technical-start guarantee.

Confidence is high in the tested one-field repair and transition plumbing.
Confidence in future profitability remains low-to-medium because exact forward
samples are sparse. A stale-extension event, restart plan mismatch, or broader
regression would falsify readiness and require a flat rollback.
