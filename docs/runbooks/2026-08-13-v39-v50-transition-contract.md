# v39 to v50 six-asset $5K transition contract

## Exact successor

The successor is
`multi_asset_growth_first_5000_six_asset_candidate_v50`, fingerprint
`375281af0b683e0ddd6c22c02b6a20ea2807705a124a1fce23da76bb39ccc7dd`.
It contains six assets, seven provider-symbol routes, and twelve directional scopes:

- BTC: Hulk robust-v3 short and liquidity-sweep long.
- ETH: repaired Range Onset long/short.
- SOL: repaired Range Onset long/short with the 80-bps stop override.
- HYPE: compression/pullback long/short.
- `xyz:SP500`: fresh15-v3 pressure long/short.
- `xyz:SPCX`: fresh15-v3 pressure long/short.

The four core provider objects are identical to repaired v49. The two index
routes use the distinct fresh15-v3 durable-journal adapter; retired v2 is not
restored or relabeled. No new profit target or trailing lock is introduced in
this transition. Existing stops, fixed BTC targets, opposite-intent exits, and
maximum-hold contracts remain authoritative.

## $5K sizing and bounded stress

Each asset uses 10% isolated margin and 10x position leverage. At $5,000, one
occupied slot uses $500 margin and $5,000 notional. Six occupied assets use 60%
isolated margin and $30,000 gross notional; four of the account's ten position
slots remain unused.

Exact report-only evidence is
`data/logs/research/bidirectional_cohort/v50_growth_sizing_stress_20260813_v1.json`.
The six-position sampled p99 stop wave is $299.032204, or 5.980644% of $5,000.
This is a deterministic modeled stress, not an expected loss, probability,
liquidation ceiling, or profitability gate. Gaps and unobserved states can lose
more.

## Technical boundary

Transition requires zero venue positions and zero owned orders. The first v50
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
3. Generate the exact final preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v50_final_flat_preflight.json
```

4. Create and verify the credential-free prestart backup:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <BUNDLE_FROM_PREVIOUS_JSON>
```

5. Dry-run and then publish the immutable 0/0 epoch:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v50_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v50_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v50_first_live

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v50_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v50_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v50_first_live \
  --yes
```

6. Inspect the staged profile without live authority:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --growth-preflight data/logs/research/bidirectional_cohort/v50_final_flat_preflight.json
```

7. Only after explicit operator authorization, start v50 with both live-risk
   flags and the exact accounting bundle:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v50_first_live \
  --enabled \
  --i-accept-live-risk
```

8. After all six ledgers advance, publish the technical audit:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v50_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v50_final_flat_preflight.json
```

## Acceptance and falsifiers

Require exact v50 identity, six assets, seven routes, twelve scopes, current
fees/leverage, every open position protected, current observer provenance, and
0/0 epoch accounting. Abort on any identity mismatch, stale observer, missing
route telemetry, unprotected position, venue/ledger disagreement, inherited
v39 lifecycle, or nonzero initial v50 count.

Confidence is high in the mechanically tested configuration and accounting
boundary. Profitability remains a live trial result rather than an implicit
startup gate. Realized friction above the frozen stress, wrong-side entries,
missed exits, or repeated after-cost losses update the strategy assessment.
