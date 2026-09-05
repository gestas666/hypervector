# V57 to V58 eight-asset transition contract

## Status and authority boundary

This document prepares a recoverable transition; it does not authorize one.
V58 requires explicit live approval for its exact profile, sizing, leverage,
routes, and risk envelope before any live process starts. Report-only evidence
and observer activity cannot place orders.

The successor is
`multi_asset_growth_first_5000_eight_asset_incremental_v58`, fingerprint
`8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b`.
Its config is
`configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml`,
SHA-256
`1c1c1656233b074df2ed3adcee8cb8cb2c58f0d191cc9f9ac34799478fca3378`.

V58 contains exactly 4 crypto and 4 non-crypto assets:

- `BTC`: robust-v3 and tuned-v2 HULK shorts plus the 60/60 sweep long.
- `ETH`: compression-pullback breakout, long and short.
- `SOL`: generic tuned-v2 HULK, short authority only.
- `HYPE`: compression-alignment v2, long and short.
- `xyz:SP500`: receipt-causal fresh15 pressure v3, long and short.
- `xyz:SPCX`: cash-open gap reversal, short authority only.
- `xyz:SNDK`: fresh15 commodity pressure, short authority only.
- `xyz:BRENTOIL`: fresh15 commodity pressure, long and short.

There are nine providers, ten provider-symbol routes, and fourteen executable
direction scopes. `maximum_positions=10` is account capacity; one position per
symbol makes the effective configured maximum eight. No generic HYPE strategy
is transferred to another asset.

## Exit and risk contracts

- BTC HULK: structural stop clamped to 20–75 bps, 3R target, 24-hour maximum.
- BTC sweep: fixed 60-bps stop and target, 24-hour maximum.
- ETH: fixed 60-bps stop, eligible opposite intent closes without same-cycle
  reversal, no fixed target, 12-hour maximum.
- SOL HULK: structural stop clamped to 20–75 bps, 3R target, 24-hour maximum.
- HYPE: fixed 80-bps stop, eligible opposite intent close, no fixed target,
  eight-hour soft hold with fresh regime-supported extension to 24 hours.
- SP500: fixed 80-bps stop, completed-bar 100/40/80-bps profit lock, eligible
  opposite intent close, 24-hour maximum.
- SPCX: fixed 80-bps stop, prior cash close absolute target, provider recipe
  exits, and 22,500-second maximum.
- SNDK and BRENTOIL: fixed 80-bps stop, no fixed target, eligible opposite
  intent close, and 24-hour maximum.

Sizing uses isolated margin. BTC and HYPE each use 10x, 10% margin, and a
$5,000 cap; SP500 and SPCX each use 5x, 7% margin, and a $1,750 cap; ETH, SOL,
SNDK, and BRENTOIL each use 5x, 3% margin, and a $750 cap. All eight together
configure 46% initial margin and $16,500 gross notional against the explicit
$5,000 sizing reference.

The exact V58 stress artifact is
`data/logs/research/bidirectional_cohort/v58_eight_asset_growth_sizing_stress_20260819_v1.json`,
SHA-256
`25e95bdd6857b486bcffb9d0fa102712e1687cbe4e0b75dcd2553085bdd13c85`.
Its deterministic simultaneous stacked p99 stop-wave result is $180.3042, or
3.6061% of $5,000. This is neither a joint probability nor a loss ceiling.
Gaps, liquidation mechanics, stale books, correlation, or worse execution can
lose more. The maximum isolated margin committed across eight positions is
$2,300.

## Evidence quality and trial interpretation

Technical configuration confidence is high from provider validation, collector
construction, route-direction tests, observer coverage, stress binding,
post-start acceptance tests, and 160x50 TUI rendering.

Profitability confidence is low and uneven. BTC/HYPE are retained live-research
incumbents rather than proven edge. ETH has one prior exact long loss and a
second report-only long still open. SOL has positive pooled historical shorts
but negative validation and one manually closed canary short. SP500 has only
one exact profitable short and no exact long. SPCX short is development-
promising but historical mark paths are incomplete. SNDK and BRENTOIL have
adverse or insufficient native evidence. These facts do not create a hidden
performance gate under `SRS_HV1_NO_GATES`; they disclose the risk of an
explicitly approved empirical live trial.

The V58 observer run `bidirectional-observe-1787127644202` has evaluated all ten
provider-symbol routes. Its observations are not live fills and must not be
merged into the new accounting epoch.

## Preconditions at the transition boundary

Do not start V58 unless all conditions hold simultaneously:

1. The operator explicitly approves this exact V58 profile and envelope.
2. Venue and every V57 ledger are flat with zero owned orders.
3. No live backend or checkpoint writer owns either runtime lock.
4. The V58 config and stress hashes match this document.
5. A fresh mainnet preflight reports all eight assets, exact fees/leverage/depth,
   `flat_no_orders=true`, `ledger_reconciled=true`, and no readiness reasons.
6. A fresh credential-free prestart backup verifies independently.
7. A new V58 accounting epoch binds the final checkpoint, preflight, backup,
   config, and starting equity.

The latest preliminary V58 preflight is
`data/logs/research/bidirectional_cohort/v58_eight_asset_preflight_20260819_v5.json`,
SHA-256
`3f6382fb91ba6b24077fc1694837cabd2c86b1f5a44151d1aa3996fcba44067a`.
At 2026-08-19 09:47:18Z it found $4,875.838 account value, all eight assets
flat, zero orders, exact ledger reconciliation, current fees and complete
visible depth at every planned notional. It is point-in-time evidence and
cannot be reused as the final post-approval cutover boundary.

## Final preflight, backup, and accounting epoch

After approval and after stopping the V57 checkpoint writer and V58 observer,
preserve their final ledgers and checkpoints. Generate a fresh preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --active-config configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v58_final_flat_preflight.json
```

Create and independently verify the credential-free source backup. Record the
bundle path printed by the first command as `<V58_PRESTART_BUNDLE>`:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <V58_PRESTART_BUNDLE>
```

Dry-run the exact rollover, inspect the result, then publish it once:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml \
  --successor-config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v58_final_flat_preflight.json \
  --prestart-bundle <V58_PRESTART_BUNDLE> \
  --epoch-id v58_eight_asset_incremental_8a04636c_r1 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r1

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml \
  --successor-config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v58_final_flat_preflight.json \
  --prestart-bundle <V58_PRESTART_BUNDLE> \
  --epoch-id v58_eight_asset_incremental_8a04636c_r1 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r1 \
  --yes
```

The new epoch must make the V58 cockpit show ALL-TIME 0/0 and CURRENT RUN 0/0
while preserving older ledgers and research history outside the epoch.

## Live start, checkpoint, post-start acceptance, and TUI

Only after the boundary above passes, start V58 with both explicit risk flags:

```bash
uv run python scripts/multi_asset_bidirectional_live.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r1 \
  --enabled --i-accept-live-risk
```

Capture the exact startup run ID and start the checkpoint writer with that ID:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --run-id <V58_RUN_ID_FROM_STARTUP> \
  --research-database data/research/market.duckdb \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r1 \
  --research-sync-interval-seconds 120 --venue-portfolio \
  --disable-asymmetric-forward-observer
```

After every provider-symbol route has produced at least one post-start
evaluation, publish the immutable technical acceptance:

```bash
uv run python scripts/v58_poststart_acceptance.py \
  --stress data/logs/research/bidirectional_cohort/v58_eight_asset_growth_sizing_stress_20260819_v1.json \
  --preflight data/logs/research/bidirectional_cohort/v58_final_flat_preflight.json
```

It must accept exact identity, 8 assets, 10 routes, 14 direction scopes, 46%
margin envelope, all provider exits, bound plans, pressure freshness, and no
inherited V57 lifecycle.

The attach-only TUI command is:

```bash
cd /Users/gestas/Prototypes/hypervector && \
CARGO_TARGET_DIR=/tmp/hypervector-v58-cargo \
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v58_eight_asset_incremental_8a04636c_r1 \
  --refresh-ms 500
```

## Rollback and falsifiers

Rollback is allowed only from a verified flat and order-free V58 boundary.
Preserve V57/V58 ledgers, observer prefixes, checkpoints, preflights, backups,
epochs, stress evidence, and acceptance reports. Never relabel observer or V57
outcomes as V58 live evidence.

Abort the cutover or stop new entries on any profile, hash, epoch, lock, venue,
ledger, fee, route, direction, source, stop, target, profit-lock, recipe-exit,
protection, or accounting mismatch; any duplicate owned order; any inherited
open lifecycle; any initial epoch count other than 0/0; or failed post-start
acceptance. A strategy loss updates empirical evidence but is not itself a
technical-start failure unless the operator explicitly changes the trial.

Confidence is high in the tested topology and transition mechanics, medium in
the frozen stress arithmetic, and low in future profitability. A fresh
preflight or post-start acceptance failure falsifies operational readiness.
Resolved forward losses, cost overruns, or correlated stops would update the
economic assessment and could support a separately approved route or sizing
change.
