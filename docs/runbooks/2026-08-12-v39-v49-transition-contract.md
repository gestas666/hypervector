# v39 to v49 repaired-growth transition contract

## Authority and exact successor

This runbook prepares, but does not authorize, a flat-boundary transition from
the active v39 profile to
`multi_asset_growth_first_5000_repaired_candidate_v49`, fingerprint
`0be937a1a50ca56becefb330f96d770e39863727d1e2832d025474afc489ae5e`.
The exact source-bound stress evidence is
`data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json`.

The runbook, observer, preflight, and acceptance report cannot place, cancel,
resize, or close an order. Live startup remains separately authorized by the
operator and requires both explicit live-risk flags.

## Exact v49 roster and repair

v49 retains four assets, five provider-symbol routes, and eight directional
scopes:

- BTC Hulk short v3: completed 30-minute setup, structural 20--75 bps stop,
  3R target, and 24-hour terminal fallback.
- BTC liquidity-sweep long: hourly setup, 60 bps stop and target, and 24-hour
  terminal fallback.
- ETH Range Onset: completed hourly cross plus completed five-minute structure,
  active dual-MTF non-opposition context, 60 bps stop, strategy/opposite-signal
  exit, and 48-hour terminal fallback.
- SOL Range Onset: the same signal family, but an exact per-symbol 80 bps stop,
  strategy/opposite-signal exit, and 48-hour terminal fallback.
- HYPE compression breakout/pullback: completed five-minute onset plus pullback,
  80 bps stop, strategy exit, 8-hour soft hold, and regime-supported extension
  no later than the 24-hour hard fallback.

The SOL override repairs v48 configuration drift: v48 applied the provider's
ETH 60 bps default to SOL although the frozen SOL forward recommendation used
80 bps. The supporting comparison remains statistically inconclusive, so this
is exact contract reconciliation rather than a claim that 80 bps is optimal.
v48 is preserved and must not be edited or presented as v49 evidence.

Removed HIP-3 pressure, HIP-3 Swing, HT onset transfers, and old bidirectional
Hulk routes remain absent. Their isolated winners do not overcome validation,
after-cost, or largest-winner sensitivity defects. A future versioned causal
redesign may be tested; unchanged identities are not restored by this runbook.

## $5K sizing and stress interpretation

Each configured asset uses 15% isolated margin at fixed 10x leverage. At the
$5,000 reference, an active asset can use $750 margin and $7,500 notional.
Only four simultaneous positions are possible because v49 has four assets,
although the account capacity remains ten. Fully occupied configured margin is
60% of equity.

The exact modeled p99 stop wave is `$309.297924`, or `6.185958%` of the $5,000
reference. This is a sampled, deterministic friction scenario. It is not an
expected loss, maximum loss, liquidation ceiling, probability forecast, or
profitability claim. Stop overrun, correlated gaps, latency, and unobserved
market states can produce a larger loss.

## Recoverable clean accounting epoch

The first v49 live run must begin as a recoverable clean accounting epoch. The
cockpit acceptance state is **ALL-TIME 0/0** and **CURRENT RUN 0/0** before any
v49 order is permitted. This is a new reporting epoch, not a claim that the v39
history never happened.

At the flat and order-free boundary, create the mandatory prestart bundle and
verify it independently with `scripts/cohort_prestart_backup_verify.py`. Then
publish an immutable logical boundary with
`scripts/cohort_accounting_rollover.py`. The boundary records exact hashes of
the final checkpoint, final preflight, and preserved prestart manifest.

The source ledgers and historical projection remain append-only. No ledger, checkpoint, or archive is moved,
deleted, truncated, or rewritten. Instead,
the first v49 accounting view includes only lifecycles matching the exact v49
profile fingerprint whose exit timestamp is at or after the recorded epoch
start. The preserved v39 history remains independently readable, while the
v49 cockpit begins at zero under an explicit accounting identity.

Before live-risk flags are accepted, a transition acceptance test must prove:

- the venue and every v39 ledger are flat and own zero orders;
- the preserved v39 epoch is independently readable and hash-verified;
- the fresh v49 checkpoint has zero closed and zero open lifecycles;
- both TUI accounting scopes render **ALL-TIME 0/0** and **CURRENT RUN 0/0**;
- current venue equity is shown without importing v39 PnL into the new epoch.

Any inherited lifecycle, missing preserved evidence, nonzero v49 epoch count,
or accounting identity mismatch aborts v49 startup. Direct backend, checkpoint,
and unified TUI launch paths all require the exact bundle for this v49 profile.

## Flat-boundary procedure

1. Keep v39 managing its current position and owned reduce-only protection.
2. Wait for **zero venue positions and zero owned orders** across every v39
   ledger. Any venue/ledger disagreement aborts transition work.
3. Stop v39 normally only at that boundary. Preserve its final checkpoint,
   ledgers, archive, and prestart backup; verify backend and checkpoint writer
   have exited.
4. Generate a fresh boundary preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json
```

5. Require exact v49 identity, current fees and leverage, candidate-notional
   depth, reconciled ledgers, and zero positions/orders. A stale or mismatched
   preflight is unusable.
6. Create and independently verify a credential-free v49 prestart bundle. Use
   the exact `bundle` path printed by the first command in the second command
   and in the rollover command below:

```bash
uv run python scripts/cohort_prechange_backup.py \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab

uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle <BUNDLE_FROM_PREVIOUS_JSON>
```

7. Dry-run the logical epoch, inspect the JSON summary, then publish it once.
   The output is immutable and intentionally named for the first v49 live run:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v49_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v49_first_live

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --successor-config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json \
  --prestart-bundle <BUNDLE_FROM_PREVIOUS_JSON> \
  --epoch-id v49_first_live \
  --out data/backups/bidirectional_cohort/accounting_epochs/v49_first_live \
  --yes
```

8. Inspect the staged profile through the attach-only cockpit:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --growth-preflight data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json
```

9. Require four assets, five routes, eight side scopes, exact ETH 60 bps and
   SOL 80 bps plans, active/staged identity separation, and no missing cockpit
   telemetry.
10. Only after separate operator authorization may v49 start. The unified
    launcher must receive the exact immutable accounting bundle:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v49_first_live \
  --enabled \
  --i-accept-live-risk
```

11. After all four ledgers advance, publish the generic live audit and exact
   report-only technical acceptance:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v49_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json
```

## Monitoring, rollback, and falsifiers

Track provider net PnL, return on margin, PF, drawdown, fees, funding,
largest-winner removal, eligible-but-missed setups, exit reasons, and exact
regime context. Preserve every strategy version before mechanism changes.
Rollback only while v49 is flat and order-free.

Confidence is high that identity checks separate v49 from v48 and bind the SOL
override. Confidence in profitability is low-to-medium because compatible v49
live closes do not yet exist. Reassess if a fresh preflight changes venue
constraints, any entry binds the wrong stop, post-start identity/protection
fails, realized friction exceeds the stress model, or retained route outcomes
remain negative across compatible forward samples.
