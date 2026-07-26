# Hypervelocity shadow friction batch 2 review

Date: 2026-07-26

Scope: no-submit Hypervelocity shadow execution only. This review does not arm
live trading and does not change regime eligibility, position sizing, re-entry,
or target rules.

## Outcome

No critical or high-severity defect remains in the reviewed change set. The
batch replaces the full-at-mark liquidation approximation with archived public
mark/funding context, fresh displayed-L2 market execution, documented partial
liquidation/cooldown behavior, and an explicit isolated backstop-transfer
accounting model.

Confidence: medium-high for code-path correctness because focused unit,
integration, restart, and full offline suites pass. Confidence remains medium
for exact venue fidelity until a real account liquidation record can be compared
against shadow output.

## Verified components

1. `activeAssetCtx` is subscribed beside L2 and trades, parsed from a sanitized
   live-shape fixture, archived separately, and never given a fabricated
   exchange timestamp.
2. Mark, oracle, and hourly funding observations update backend cost/mark
   authority. The TUI remains a ledger consumer and no user-visible simulation
   authority was added.
3. Liquidations require fresh continuous L2 evidence. A stale or missing book
   records uncertainty and cannot fabricate a fill.
4. Positions above $100,000 send a 20% first market attempt. A successful
   partial attempt starts a durable 30-second cooldown; attempts inside the
   cooldown use the full remaining position.
5. Market liquidation walks displayed bids for longs and asks for shorts,
   records VWAP and taker cost, cancels stale targets, and immediately restores
   reduce-only target coverage for a surviving position.
6. If displayed depth is insufficient and post-attempt equity is below
   two-thirds of maintenance, the remaining isolated position and margin are
   modeled as a backstop transfer. The ledger separately records market-filled
   and transferred quantities and preserves portfolio/port equity parity.
7. Restart restores partial-liquidation cooldown, open targets, costs, and
   position state. A declared fingerprint migration permits the previous
   full-at-mark model to adopt this batch without fabricating a fill.
8. The faithful TOML fixes all venue-mechanics values and rejects incompatible
   alternatives. These mechanics report execution outcomes; they add no
   strategy gate or performance abort condition.

## Official-source comparison

- Hyperliquid documents the >$100,000 20% partial attempt and 30-second
  cooldown, book-first liquidation, no separate clearance fee, and isolated
  backstop transfer below two-thirds of maintenance:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations>
- The documented public subscription is `activeAssetCtx`; it carries perps
  funding, mark, oracle, and open-interest context:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions>
- Configured tier-0 perp fees remain 0.045% taker and 0.015% maker:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees>
- Funding remains an hourly transfer:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding>

## Residual risks and falsification

1. `activeAssetCtx` currently lacks a venue timestamp, so the archive explicitly
   uses local receipt time. Clock skew or a future schema change would invalidate
   timing assumptions. A feed message with a genuine exchange timestamp should
   trigger a schema/model revision.
2. Public L2 exposes displayed depth, not hidden or future liquidity. Real
   liquidation fills materially outside the modeled VWAP would falsify the
   current depth model.
3. The backstop ledger uses a transfer-equivalent composite accounting price so
   the isolated margin transfer can be represented in the existing portfolio
   engine. A real `userFills` record whose final account equity disagrees would
   require replacing this model.
4. Fee configuration represents the base tier. Address-specific rolling-volume,
   staking, referral, or maker-rebate effects may lower actual cost. Comparing
   the eventual canary account's `userFees` response would update this setting.
5. The active pre-change shadow process intentionally was not restarted. It
   continues with the code loaded at its launch; this batch becomes active only
   on the next normal supervised restart.

## Validation evidence

- Focused parser/archive/session/profile/restart/liquidation tests: pass.
- Complete offline Python suite: 592 passed, 4 network tests deselected, 31
  warnings.
- Rust TUI suite: 23 passed. Cargo formatting also passed.
- CLI status: healthy and paper remains no-submit; live remains fail-closed.
- Faithful TOML parse/profile validation and Python compilation: pass.
- Bounded official-mainnet public-feed smoke: received and parsed L2, trades,
  and `activeAssetCtx`; no credentials or order client were used.
- Changed-file Ruff format/check and `git diff --check`: pass.

The validation threshold passed. The live shadow process remained untouched;
the exact reviewed commit is ready for integration. Any future accounting
parity, restart, no-submit, or public-feed failure should block deployment.
