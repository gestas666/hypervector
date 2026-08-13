# v39 to v51 profit-protected six-asset $5K transition contract

## Exact successor

The successor is
`multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51`, fingerprint
`30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908`.
It contains six assets, seven provider-symbol routes, and twelve directional
scopes:

- BTC: Hulk robust-v3 short and liquidity-sweep long.
- ETH: repaired Range Onset long/short.
- SOL: repaired Range Onset long/short with the 80-bps stop override.
- HYPE: compression/pullback long/short.
- `xyz:SP500`: fresh15-v3 pressure long/short.
- `xyz:SPCX`: fresh15-v3 pressure long/short.

The four core provider objects are identical to repaired v49. The index entry
provider remains fresh15-v3; retired v2 and legacy v1 are not relabeled.

## Exact exit contracts

- BTC Hulk short: structural stop clamped to 20–75 bps, 3R target, 24-hour
  fallback.
- BTC liquidity-sweep long: fixed 60-bps stop, fixed 60-bps target, 24-hour
  fallback.
- ETH Range: fixed 60-bps stop, qualified opposite-intent close, 48-hour
  fallback.
- SOL Range: fixed 80-bps stop, qualified opposite-intent close, 48-hour
  fallback.
- HYPE compression: fixed 80-bps stop, qualified opposite-intent close,
  eight-hour soft timer extended only while regime-supported, 24-hour hard
  fallback.
- SP500/SPCX pressure: fixed 80-bps stop, qualified opposite-intent close,
  24-hour fallback, and completed-bar trailing profit protection.

Index profit protection uses a 100-bps activation, 40-bps minimum locked gain,
and 80-bps peak giveback. It has no fixed profit target, so it does not cap a
large trend. The controller journals the causal completed-bar trigger before a
reduce-only current-price close, replays the same decision after restart, and
fails visibly on missing holding candles. The 80-bps venue stop remains the
loss backstop.

## $5K sizing and bounded stress

Each asset uses 10% isolated margin and 10x position leverage. At $5,000, one
occupied slot uses $500 margin and $5,000 notional. Six occupied assets use 60%
isolated margin and $30,000 gross notional; four of ten capacity slots remain
unused.

Exact report-only evidence is
`data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json`.
The six-position sampled p99 stop wave is $299.152584, or 5.983052% of $5,000.
This is a deterministic modeled stress, not an expected loss, probability,
liquidation ceiling, or profitability gate. Gaps and unobserved states can lose
more.

## Technical boundary

Transition requires zero venue positions and zero owned orders. The first v51
cockpit must show **ALL-TIME 0/0** and **CURRENT RUN 0/0** through a recoverable
accounting epoch. Historical v39 evidence remains append-only and preserved;
it is excluded from the new reporting epoch rather than deleted.

The fresh15 v3 observer for each index must be running and its latest status,
cursor, and decision journal must agree on provider, profile, symbol, completed
15-minute boundary, prospective delay, and fresh L2 provenance. Missing or
stale observer evidence is a technical failure and aborts startup.

## Flat-boundary procedure

1. Keep v39 managing all current positions and venue stops until the chosen
   transition boundary.
2. Require every v39 ledger and the venue to be flat and order-free, then stop
   v39 normally. Verify both backend and checkpoint writer exited.
3. Stop any older index observer processes, preserve their existing cursor and
   journal paths, then start both observers from the reviewed committed source
   in separate supervised terminals:

```bash
uv run python scripts/index_hip3_breakout_shadow_observe.py \
  --symbol xyz:SP500

uv run python scripts/index_hip3_breakout_shadow_observe.py \
  --symbol xyz:SPCX
```

   Wait for both status files to advance past their preserved cursors. Do not
   delete or reset the cursors to manufacture fresh evidence.
4. Generate the exact final preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v51_final_flat_preflight.json
```

5. Create and verify the credential-free prestart backup:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <BUNDLE_FROM_PREVIOUS_JSON>
```

6. Dry-run and publish the immutable 0/0 epoch:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v51_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v51_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v51_first_live

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v51_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v51_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v51_first_live \
  --yes
```

7. Inspect the staged profile without live authority:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v51_first_live \
  --growth-preflight data/logs/research/bidirectional_cohort/v51_final_flat_preflight.json
```

8. Only after explicit operator authorization, start v51:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v51_first_live \
  --enabled \
  --i-accept-live-risk
```

9. After all six ledgers advance, publish the technical audit:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v51_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v51_final_flat_preflight.json
```

## Acceptance and falsifiers

Require exact v51 identity, six assets, seven routes, twelve scopes, current
fees/leverage, every open position protected, exact profit-lock execution-plan
fields, current observer provenance, and 0/0 epoch accounting. Abort on any
identity mismatch, stale observer, missing route telemetry, unprotected
position, venue/ledger disagreement, inherited v39 lifecycle, or nonzero
initial v51 count.

Confidence is high in the mechanically tested stop/target/timer/profit-lock
plumbing. Profitability and the exact 100/40/80 index thresholds remain live
trial hypotheses. Realized friction above the stress, premature lock exits,
large post-activation giveback, wrong-side entries, or repeated after-cost
losses update the assessment.
