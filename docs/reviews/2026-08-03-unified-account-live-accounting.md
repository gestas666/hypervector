# Unified-account live accounting correction

## Problem restatement

The active multi-asset canary uses a Hyperliquid unified account. Its ledger
reported a larger equity increase than could be explained by position PnL,
fees, and funding. Correct account values are required for TUI telemetry,
portfolio sizing, audit output, and later strategy comparisons.

Success criteria:

- unified equity comes from the venue-authoritative spot USDC total;
- isolated collateral is deducted once when calculating available balance;
- per-position margin, notional, unrealized PnL, and liquidation values remain
  available as separate facts;
- standard-account parsing remains unchanged;
- the correction is covered by both SOL-specific and symbol-parameterized
  parser tests.

## Authoritative semantics

Hyperliquid documents `spotClearinghouseState` as the source of truth for the
trading account balance across spot and perpetuals when unified account or
portfolio margin is enabled:

- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot>

Hyperliquid also states that individual perpetual DEX user states are not
meaningful for unified-account balances. Its unified-account ratio example
uses the spot token total and deducts isolated position margin once when
calculating available collateral:

- <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes>

## Reproduced defect

The prior unified parsers performed both of these operations:

```text
account_value = usdc_total + sum(position unrealized PnL)
available = usdc_total - usdc_hold - sum(position margin)
```

The observed venue state had a USDC hold equal to total isolated margin. The
ledger therefore added open PnL twice and deducted isolated margin twice.

One live snapshot supplied this independent accounting identity:

```text
open unrealized PnL   +0.374520 USD
entry fees            -0.021359 USD
funding credits       +0.002756 USD
expected equity move  +0.355917 USD
```

The corrected venue-total equity moved by exactly `+0.355917 USD` from the
flat run baseline. The prior ledger value moved by approximately the expected
amount plus open unrealized PnL again.

## Correction

Unified parsing now uses:

```text
account_value = usdc_total
available = max(0, usdc_total - usdc_hold)
```

Position PnL, margin, notional, leverage, and liquidation price continue to be
parsed independently. Legacy standard-account parsing still uses the
perpetual clearinghouse `accountValue` and `withdrawable` fields.

## Validation evidence

- The new regression reproduced both double counts before implementation:
  three assertions failed with the expected inflated equity and depressed
  available balance.
- The same regression passed after the two parser paths were corrected.
- `62` focused venue, stream, adapter, live-script, and audit tests passed.
- A broader Hyperliquid and multi-asset live subset passed `71` tests.
- Ruff passed on the modified production and test files.
- The live audit now reports provisional economics for open positions instead
  of zero-shaped closed-trade totals.
- The live audit derives realized fee rates from each fill's fee, price, and
  size. The first two mainnet entries measured `4.3196` and `4.3197 bps`.
- All `85` affected Python tests and all `136` Rust TUI tests passed after the
  balance-source telemetry was added.

## Confidence and failure modes

Confidence: high for unified USDC equity, supported by official venue
documentation, raw mainnet observations, and an exact live accounting
identity.

Confidence: medium-high for `total - hold` as immediately available USDC. It
matches the observed isolated-margin hold and the documented single-deduction
model. This conclusion would need revision if a future official payload shows
that `hold` excludes a separately applicable withdrawal reservation.

The active process loaded the old parser before this correction. It must not
be restarted while open positions still depend on it. Its historical ledger
rows remain immutable observations and should be interpreted with this
documented correction; a safe later restart will load the fixed parser.
