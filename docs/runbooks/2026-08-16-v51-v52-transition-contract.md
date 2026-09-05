# v51 to v52 evidence-bound $5K transition contract

## Exact successor

The staged successor is
`multi_asset_growth_first_5000_evidence_bound_successor_v52`, fingerprint
`662d28b352cfc4f09e08c71ee67c8f044421483f2932539b09ea082b5e4f27f7`.
It has two executable assets, three provider-symbol routes, and four directional
scopes:

- BTC short: `hulk_expansion_short_robust_v3`.
- BTC long: `liquidity_sweep_long_1h_stop60_target60_v2`.
- HYPE long and short: `hype_breakout_compression_alignment_bidirectional_v2`.

`range_onset_bidirectional_v1` is retired from v52. ETH and SOL therefore have
no v52 execution authority. SP500 and SPCX are also absent: their source-native
forward evidence does not support another full-size entry. The ten-position
setting remains account capacity; this two-asset profile can hold at most two
positions because each asset is limited to one position.

## Exact entry and exit contracts

- BTC Hulk short: completed 30-minute mechanism, structural stop clamped to
  20-75 bps, 3R target, and 24-hour fallback.
- BTC sweep long: completed one-hour sweep, fixed 60-bps stop, fixed 60-bps
  target, and 24-hour fallback.
- HYPE alignment v2: completed one-minute compression onset only when the
  causal breakout side agrees; fixed 80-bps stop; eligible aligned opposite
  signal closes the position; eight-hour soft deadline extends only while the
  frozen regime policy supports the position; 24-hour hard fallback.

The HYPE repair changes only entry admission and strategy identity. It does not
add a fixed target or alter the native v51 stop/timer/opposite-exit mechanics.

## $5K sizing and bounded stress

Each occupied asset uses 10% isolated margin and 10x position leverage. At
$5,000, that is $500 margin and $5,000 maximum notional per position. Two
simultaneous positions use 20% isolated margin and $10,000 gross notional.

Exact report-only evidence is
`data/logs/research/bidirectional_cohort/v52_growth_sizing_stress_20260816_v1.json`.
The actual two-position sampled p99 stop wave is **$92.847534**, or **1.856951%**
of $5,000. This deterministic scenario includes the configured 80-bps asset
backstop, measured effective round-trip fee, measured p99 visible exit depth,
and a 24-hour funding sensitivity. It is not a probability forecast or loss
ceiling; gaps, latency, liquidation mechanics, and adverse selection can lose
more. The artifact's synthetic ten-slot row is not v52 exposure and must not be
presented as such.

## Required flat boundary

Keep the active v51 transition drain in force. The current protected SOL and
SPCX lifecycles retain their bound venue stops and exit controllers. Do not
manually weaken protection or restore v51 entries.

Transition requires zero venue positions and zero owned orders. The completed
drain and final v51 ledger/accounting evidence must be archived before stopping
the backend. The first v52 cockpit must show **ALL-TIME 0/0** and **CURRENT RUN
0/0** through a new recoverable accounting epoch. Prior v51 evidence is
preserved append-only rather than deleted.

## Current attach-only staged TUI

While v51 is still draining, this command is attach-only. It must not start,
stop, or arm either backend:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --staged-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml
```

After the final flat preflight and epoch exist, add:

```bash
  --growth-preflight data/logs/research/bidirectional_cohort/v52_final_flat_preflight.json \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v52_first_live_662d28b
```

## Flat-boundary procedure

1. Wait for v51 SOL and SPCX to resolve through bound exits. Require the
   transition drain to report completed, all v51 asset ledgers flat, and zero
   owned venue orders.
2. Capture the final fresh v51 checkpoint and audit. Reconcile current-run and
   accounting-epoch closes, PnL, fees, funding, and final protected-exit reasons.
3. Stop v51 normally only after the flat/order-free evidence is durable. Verify
   both backend and checkpoint writer exit.
4. Generate the exact credential-free prestart backup:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <BUNDLE_FROM_PREVIOUS_JSON>
```

5. Generate the exact public-wallet final preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --active-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v52_final_flat_preflight.json
```

   Require exact profile/fingerprint, current fee/leverage/depth evidence,
   technically ready, zero venue positions and zero owned orders, and exact
   retired-asset reconciliation.
6. Dry-run, then publish the immutable clean epoch:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --successor-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v52_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v52_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v52_first_live_662d28b

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml \
  --successor-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v52_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v52_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v52_first_live_662d28b \
  --yes
```

7. Inspect the staged TUI with the final preflight and clean epoch. Require
   v51 active identity, v52 staged identity, two assets, three routes, four
   sides, the correct exit contracts, and 0/0 epoch projection.
8. Start v52 only when every prior check remains fresh:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v52_first_live_662d28b \
  --enabled --i-accept-live-risk
```

9. After both asset ledgers advance, run the exact live audit and confirm that
   no retired route, opposed HYPE onset, or inherited v51 lifecycle appears.

```bash
uv run python scripts/v52_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v52_final_flat_preflight.json
```

   Require an explicit `accepted` result before treating the v52 startup as
   technically complete. A rejected report does not submit, resize, or close an
   order; keep new entries stopped and correct the reported mismatch.

## Rollback and falsifiers

Rollback is permitted only from a flat and order-free v52 boundary. Preserve
every v51 and v52 ledger, epoch, backup, checkpoint, and audit. Never reuse a
v52 epoch with another profile fingerprint.

Abort startup or stop new entries on any of these falsifiers:

- Profile, implementation, epoch, checkpoint, or venue identity mismatch.
- Any Range Onset, SP500, or SPCX executable action under v52.
- Any HYPE entry with opposed or unavailable breakout-side alignment.
- Missing venue protection, duplicate owned order, stale entry at submission,
  or ledger/venue disagreement.
- Initial v52 accounting other than ALL-TIME 0/0 and CURRENT RUN 0/0.
- Realized friction materially above the exact stress evidence.
- Repeated route losses or growing largest-winner dependence that contradicts
  the staged evidence.

Confidence is high in the tested profile composition and execution-contract
plumbing. Confidence in future profitability is low-to-medium because forward
samples are sparse. Additional exact closes can strengthen or falsify the
economic disposition without changing these technical acceptance gates.
