# v53 to v55 incremental SPCX transition contract

## Exact successor and scope

The successor is
`multi_asset_growth_first_5000_spcx_cash_open_v55`, fingerprint
`e918f81e55abb36ad207a1af69517dd4d8765b79eb972669195a6b180702d3c7`.
Its config SHA-256 is
`688d0dd225489e786a821372ede2ef4eda3cf5a56070cfdb56488156c5e689fb`.

This is an additive change. **BTC and HYPE remain unchanged** from v53:

- BTC short: `hulk_expansion_short_robust_v3`, 30-minute decisions, structural
  stop clamped to 20–75 bps, 3R target, 24-hour fallback.
- BTC long: `liquidity_sweep_long_1h_stop60_target60_v2`, hourly decisions,
  fixed 60-bps stop and target, 24-hour fallback.
- HYPE long/short: `hype_breakout_compression_alignment_bidirectional_v2`,
  one-minute decisions, fixed 80-bps stop, eligible opposite-signal exit,
  eight-hour soft deadline with fresh regime-supported extension, and 24-hour
  hard deadline.

The only new route is `xyz:SPCX` long/short through
`hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1`. It evaluates the
completed 09:30–09:45 New York cash-open candle from receipt-causal public
trades. A still-open gap of at least 20 bps is faded toward the previous
eligible cash-session close. The prior close is a dynamic absolute target.
The route also has an 80-bps venue stop, cash-session/source-recovery recipe
exit, and 22,500-second fallback.

## Evidence and confidence

The frozen development artifact is
`data/logs/research/xyz_spcx_cash_open_gap_reversal_development_20260817_v2.json`.
It contains 20 development trades, approximately **3.9 development trades/week**,
nominal net +$507.30/PF 2.08 and stress net +$418.13/PF 1.82 at
$5,000 notional. Stress remained +$225.28 after removing the largest winner.

This is not qualified edge evidence. Validation and holdout were not accessed,
and **11 of 20** historical entry lifecycles have unresolved exact mark paths.
The disposition remains `NOT_SUITABLE_TECHNICALLY_UNRESOLVED`. The live route
is therefore an explicitly aggressive forward-research trial, not a claim of
proven profitability. The route must not be copied to another asset from this
evidence.

Technical confidence is high after focused and full-suite verification.
Profitability confidence is low-to-medium. A source gap, incorrect dynamic
target, missing stop, missed recipe exit, or materially worse live costs would
falsify technical readiness. Forward losses, sparse firing, or dependence on
one winner would update the economic assessment downward.

## Sizing and loss sensitivity

All three assets use 10x isolated leverage, 10% account margin, and a $5,000
notional cap per position. Three simultaneous positions reserve $1,500, or 30%
of the $5,000 reference account; the 10-position setting is portfolio capacity,
not a claim that 10 assets are configured.

The v53 BTC/HYPE componentwise p99 stop-wave artifact reports $92.7922. SPCX's
frozen 80-bps stop plus 27.4209-bps stress round-trip execution cost is $53.7104
at $5,000 notional. Their arithmetic sum is approximately $146.50, or 2.93% of
$5,000. This combines different evidence windows and is a deterministic
sensitivity, not a joint probability, loss ceiling, or liquidation bound.
Gaps and adverse execution can lose more; total isolated margin at risk is
$1,500.

## Frozen technical evidence

The last passing report-only venue preflight is
`data/logs/research/bidirectional_cohort/v55_candidate_flat_preflight_20260818T1000Z_v2.json`,
SHA-256 `92804228c032ee2a457f969eb374f8402bae648ff098cb9ef6bf076a31132ad8`.
It observed $4,917.9241 account equity, all three assets flat, zero owned orders,
current SPCX fee/depth evidence, and exact active-v53 to candidate-v55 identity.
It cannot place an order and is not the post-stop accounting boundary.

The exact verified rollover prestart bundle is
`data/backups/bidirectional_cohort/prestart_20260818T102332.344153Z_e918f81e55ab`.
Its manifest SHA-256 is
`14da3623e136434d4284151b059104a1d6c03cc3b2ab1502228a583a3929053b`
and its 1,596-file implementation SHA-256 is
`5186887a5629a0b5f83251e04e71f09c0a64b4a8d612eab7217c565a6a068e5b`.
Independently verify it before rollover:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_20260818T102332.344153Z_e918f81e55ab
```

## Flat stop and final accounting boundary

The transition boundary was completed through the authenticated drain request
`e497523e4783e5100847f257c7588c4b` on v53 run
`bidirectional-live-1787048172028`. Its immutable archive is
`data/backups/bidirectional_cohort/transition_drains/transition_drain_20260818T102109Z_e497523e4783e5100847f257c7588c4b.json`.
The final v53 checkpoint is
`data/runtime/bidirectional_cohort/v53_drain_final_checkpoint.json`; it records
BTC/HYPE flat, zero orders, terminal asset lifecycles, and a completed drain.
Do not rerun the historical stop or drain request.

The fresh post-drain final preflight was published with:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --active-config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v55_final_flat_preflight_20260818_v5.json
```

Require exact v55 identity, current fees/leverage/depth, all three assets flat,
zero orders, and exact ledger reconciliation. Dry-run, then publish a new
recoverable accounting epoch; prior v53 evidence remains append-only:

```bash
uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --successor-config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v55_final_flat_preflight_20260818_v5.json \
  --prestart-bundle data/backups/bidirectional_cohort/prestart_20260818T102332.344153Z_e918f81e55ab \
  --epoch-id v55_spcx_cash_open_r2 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v55_spcx_cash_open_e918f81_r2

uv run python scripts/cohort_accounting_rollover.py \
  --prior-config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml \
  --successor-config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --preflight data/logs/research/bidirectional_cohort/v55_final_flat_preflight_20260818_v5.json \
  --prestart-bundle data/backups/bidirectional_cohort/prestart_20260818T102332.344153Z_e918f81e55ab \
  --epoch-id v55_spcx_cash_open_r2 \
  --out data/backups/bidirectional_cohort/accounting_epochs/v55_spcx_cash_open_e918f81_r2 \
  --yes
```

## Live start, acceptance, and TUI

Arm v55 only after the final preflight, verified backup, epoch, flat venue, and
free runtime locks all agree:

```bash
uv run python scripts/multi_asset_bidirectional_live.py \
  --config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --backtest-lab-root ../backtest-lab/backtest_lab \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v55_spcx_cash_open_e918f81_r2 \
  --enabled --i-accept-live-risk
```

Start the checkpoint writer with the same config and epoch and bind it to the
exact live run; omitting `--run-id` can select an older compatible ledger:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --run-id bidirectional-live-1787048825207 \
  --research-database data/research/market.duckdb \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v55_spcx_cash_open_e918f81_r2 \
  --research-sync-interval-seconds 120 --venue-portfolio \
  --disable-asymmetric-forward-observer
```

After BTC, HYPE, and SPCX ledgers advanced, the immutable technical acceptance
was published as
`data/logs/research/bidirectional_cohort/v55_poststart_acceptance_20260818T103754Z.json`,
SHA-256 `3072a377ef107d3e70cdbb184a0f23f74e22a4143140c13c8eb00b7aeb75b0a3`:

```bash
uv run python scripts/v55_poststart_acceptance.py \
  --candidate data/logs/research/xyz_spcx_cash_open_gap_reversal_development_20260817_v2.json \
  --preflight data/logs/research/bidirectional_cohort/v55_final_flat_preflight_20260818_v5.json
```

It must accept the exact profile/fingerprint, four provider-symbol routes, six
directional scopes, SPCX public-trade readiness, dynamic target contract,
80-bps stop, recipe exit, fallback, and bound plans for any open lifecycle.

The attach-only cockpit command is:

```bash
cd /Users/gestas/Prototypes/hypervector && \
CARGO_TARGET_DIR=/tmp/hypervector-v55-cargo \
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml \
  --accounting-epoch-bundle data/backups/bidirectional_cohort/accounting_epochs/v55_spcx_cash_open_e918f81_r2 \
  --refresh-ms 500
```

## Rollback and stopping conditions

Rollback is permitted only from a flat and order-free v55 boundary. Preserve
all v53/v55 ledgers, checkpoints, preflights, backups, epochs, and acceptance
reports. Never relabel v53 outcomes as v55 evidence.

Stop new entries or fail the launch on any identity, epoch, lock, venue,
ledger, fee, route, source, target, stop, recipe-exit, protection, or accounting
mismatch; any duplicate owned order; any inherited open lifecycle; or failed
post-start acceptance. Strategy performance remains an empirical forward
result rather than a technical abort gate unless the user explicitly changes
that trial contract.
