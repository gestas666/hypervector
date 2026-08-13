# Apex-Derived Cohort Readiness Review

## Decision

No candidate demonstrated a positive offline edge under the frozen bounded budget. `apex_mean_reversion_v2` is retained as a negative control, `apex_oi_trend_v2` remains observer-only because historical point-in-time open interest is absent, and `apex_regime_mm_v2` is eligible only for a tightly capped live **measurement** canary. It is not promoted as a profitable strategy.

Confidence in that classification is high for the tested configurations because all declared development, chronological validation, and robustness passes completed with consistent evidence. Confidence in historical market-maker fill fidelity is medium-low because public L2 cannot reveal private queue rank or hidden cancellations. Real maker fills, cancel acknowledgements, and one-second markouts can update that assessment.

## Frozen Evidence

| Candidate | Segment | Activity | Net result | PF | Max drawdown | Liquidations | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| Mean reversion | Development | 1,758 trades | -$9,784.04 | 0.30 | -65.36% | 0 | Negative control |
| Mean reversion | Validation | 978 trades | -$6,260.48 | 0.48 | -41.94% | 0 | Negative control |
| Mean reversion | Robustness | 943 trades | -$8,792.70 | 0.16 | -58.62% | 0 | Negative control |
| OI trend | Development | 0/52,991 OI-covered bars | $0.00 | N/A | 0.00% | 0 | Observer only |
| OI trend | Validation | 0/25,920 OI-covered bars | $0.00 | N/A | 0.00% | 0 | Observer only |
| OI trend | Robustness | 4/25,920 OI-covered bars | $0.00 | N/A | 0.00% | 0 | Observer only |
| Regime MM | Development | 624 maker fills / 12 sampled hours | -$9.88 | 0.00 by session | -0.013% | 0 | Measurement canary only |
| Regime MM | Validation | 445 maker fills / 6 sampled hours | -$14.46 | 0.0001 by session | -0.042% | 0 | Measurement canary only |
| Regime MM | Robustness | 172 maker fills / 6 sampled hours | -$3.44 | 0.02 by session | -0.009% | 0 | Measurement canary only |

Mean market-maker one-second markout was -1.07 bps in development, -1.98 bps in validation, and -2.20 bps under the 150 ms robustness latency. That is the principal adverse-selection warning. All funding inputs came from the complete 8,760-row official Hyperliquid hourly funding bundle for 2025-07-28 through 2026-07-28.

## Shared Capital

The deterministic one-account replay gives market making priority at simultaneous BTC entry times, permits only one net position per symbol, reserves aggregate margin, and records every rejected conflict.

| Segment | Accepted | Rejected conflicts | Shared net PnL | Max drawdown |
|---|---:|---:|---:|---:|
| Development | 1,775 | 7 | -$9,784.79 | -65.31% |
| Validation | 983 | 7 | -$6,116.23 | -40.96% |
| Robustness | 949 | 6 | -$8,760.23 | -58.40% |

The combined result does not rescue mean reversion. The research/shared-capital layer supports multiple strategies with immutable attribution and one capital/inventory authority. The staged live surface currently exposes only the MM measurement canary because the directional/OI and mean-reversion candidates did not qualify; that is an evidence result, not a one-strategy architecture constraint. A future second live candidate requires integration into one in-process shared allocator rather than launching a competing backend, because the account lock intentionally rejects concurrent execution processes.

## Canary Scope

The next canary should measure execution rather than claim expected profit:

- Strategy identity: `apex_regime_mm_v2`.
- Venue/symbol: Hyperliquid mainnet BTC perpetual.
- Margin: isolated, 3x.
- Canary account assumption: approximately $150 account value, verified at preflight rather than hard-coded as venue truth.
- Maximum net BTC inventory notional: $30.
- Base post-only order notional: $12.50 per side.
- Venue minimum order notional: $10; any cascade-reduced opening leg below that value is suppressed rather than submitted.
- One net BTC position at a time; simultaneous resting bid/ask orders still resolve to one-way net venue exposure.
- Stop behavior: cancel both resting quotes, reconcile, then flatten any residual inventory and verify flat.
- Telemetry: strategy ID, quote prices/sizes, OIDs, exact cancel intents, acknowledgement round-trip latency, fills, expected-price-versus-fill slippage, account-specific fees, funding, inventory, liquidation price/distance, one-second markout, available equity, and faults.
- TUI: read-only projection of the authoritative backend ledger; no local fill or PnL simulation.

Live construction remains fail-closed and requires fresh `--enabled --i-accept-live-risk` flags plus configured credentials. This review grants no execution authority.

After a canary stops and reconciles flat, publish an immutable report-only audit from the exact live-ledger prefix:

```bash
uv run python scripts/apex_regime_mm_live_canary_audit.py \
  --decisions data/live/apex_regime_mm/decisions.jsonl \
  --out data/logs/live/apex_regime_mm_canary_audit_v1.json
```

The audit has no execution client or mutation authority. It reports sparse and losing runs without rejection, hashes the exact ledger snapshot, and separately marks missing latency, fill slippage, markout, or liquidation-distance evidence as technical gaps.

### Read-only venue preflight

At `2026-08-01T05:33:55Z`, a credential-incapable read-only query of the configured account reported BTC flat with zero BTC open orders, $153.61 account value and withdrawable balance, 1.5 bps maker fees, 4.5 bps taker fees, a $1 BTC price tick, a 0.00001 BTC size step, unified-account mode, and the configured 40x BTC venue maximum. These observations are time-sensitive and must be revalidated by the armed startup preflight.

Hyperliquid's official exchange error reference documents a $10 minimum perp order value: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/error-responses>. The live config therefore freezes that value and suppresses undersized cascade legs. A venue rule change would falsify this assumption and requires a config/code update rather than a success-shaped fallback.

## Falsifiers and Rollback

The measurement-canary rationale is falsified if account-specific minimum order size prevents the frozen order notional, paired post-only quotes cannot be reconciled reliably, cancel latency leaves uncontrolled inventory, real maker markouts remain materially negative, or backend and venue positions diverge. Any such technical failure should cancel quotes, flatten if safely reconcilable, write a fault, and stop.

Hyperliquid does not expose the canary's true private queue rank. Displayed L2 depth may support an estimate, but it must not be labeled as measured queue position. Real fill latency and post-fill markouts are the authoritative canary evidence for that uncertainty.

The profitability assessment would improve only if real, fully reconciled maker fills show positive after-fee markouts and session PnL over a materially larger sample. A few favorable fills would not establish edge. Conversely, consistently worse live markouts than replay would strengthen the negative assessment.

## Evidence Paths

- `data/logs/research/apex_cohort_apex_mean_reversion_v2_*_v1.json`
- `data/logs/research/apex_cohort_apex_oi_trend_v2_*_v1.json`
- `data/logs/research/apex_cohort_apex_regime_mm_v2_*_v1.json`
- `data/logs/research/apex_cohort_shared_*_v1.json`
- `data/cache/vendor/hyperliquid/BTC/20250728T000000000000Z_20260728T000000000000Z_funding/manifest.json`

Focused verification includes:

```bash
uv run pytest tests/test_apex_mm_live_audit.py tests/test_apex_mm_live_canary_audit_script.py -q
uv run ruff check src/hypervector/research/apex_mm_live_audit.py scripts/apex_regime_mm_live_canary_audit.py
```

## Directional Cohort Addendum

The later OG Hulk rehabilitation added `hulk_expansion_short_robust_v3` as a
BTC-only directional research survivor. This does not revise the negative Apex
candidate results above. It changes the active shared-capital set:

- Apex mean reversion remains an observer/negative control and does not own
  capital.
- Apex regime MM remains a tightly capped execution-measurement candidate.
- Hulk becomes the directional BTC candidate and receives simultaneous-entry
  priority over MM.

Aligned active-set comparisons were positive in development (+$102.35),
validation (+$381.70), and robustness (+$84.19). MM contribution remained
negative in every segment; Hulk supplied the positive result. Evidence is in
`data/logs/research/20260801_hulk_mm_active_shared_*_v1.json` and the complete
Hulk review is `docs/reviews/2026-08-01-market-cipher-strategy-rehabilitation.md`.

This addendum grants no live authority. Outcome-level comparison cannot split an
already-running MM session when a Hulk signal arrives. The runtime allocator
must cancel, reconcile, and yield BTC ownership before directional entry.

## Live Transport Addendum

The latest no-fill canary audit found that serial quote submission violated the
frozen one-second book-age contract asymmetrically: zero of 147 buy intents but
114 of 147 sell intents were older than 1,000 ms at submission. The MM adapter
and engine now submit both sides through one official-SDK `bulk_orders` action,
retain per-leg acknowledgement and rollback semantics, and publish the transport
identity to the TUI. Direct backend or supervisor `SIGTERM` also enters verified
cleanup.

This repairs an execution defect; it does not improve the negative offline MM
economics or promote the strategy. The next live batch requires fresh explicit
authorization. Any stale post-repair intent, unreconciled partial acceptance,
or non-flat shutdown falsifies transport readiness.
