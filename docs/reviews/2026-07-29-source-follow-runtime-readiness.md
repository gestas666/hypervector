# Source-follow shadow runtime readiness — 2026-07-29

## Decision

The distinct `hypervelocity_source_follow_shadow_v1` profile is ready for an
explicit fresh shadow cutover. It is not active, live-enabled, or established
as a profitable forward edge. The existing canonical backend was left running
and was not reset during validation.

## Verified contract

- Pinned source revision: `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Signal: confirmed completed-5m `TREND_DOWN` onset, short only, confidence at
  least 0.70, completed-5m range at most 100 bps, 24/7.
- Entry: decision at completed-bar availability, one 60-second post-only pulse,
  public Hyperliquid L2/trade-through evidence, one BTC position.
- Risk: $15,000 initial shadow capital, 50% isolated margin, 30x leverage.
- Exit: 8% gross-margin target, no fixed stop, range does not force-close, and
  the first fresh BBO taker execution after a 24-hour maximum hold.
- Metalabel: observe-only; it cannot filter or resize orders.

## Empirical validation

The local pinned classifier reproduced 105,120 completed five-minute bars over
the full 2025-07-28 through 2026-07-28 window with zero label mismatches. It
also reproduced all 674 transition events with zero event mismatches; 672 were
eligible entry events. This proves implementation parity with the pinned
revision, not profitability.

An integration test exercised source onset through fresh L2 maker submission,
public trade fill, ledger accounting, process reconstruction, and restoration
of the original position-open timestamp and 86,400-second deadline. Missing
hold-origin evidence fails closed. Full liquidation clears hold state, while a
partial liquidation preserves the original deadline.

Backend session identity now reports the source profile rather than inherited
canonical display values. The read-only TUI consumes and displays the profile
ID, 30x leverage, 50% allocation, source engine and side, minimum confidence,
24-hour hold, and fresh-BBO exit policy.

Verification results:

- Source/execution/TUI focused Python: 119 passed.
- Repository non-network Python: 1,417 passed, 4 deselected, 0 failed.
- Rust TUI: 34 passed, 0 failed.
- CLI status: `ok=true`; paper default remains shadow/no-submit; live remains
  fail-closed.

## Immutable evidence

- Full-year runtime parity:
  `data/logs/research/hypervelocity_source_runtime_parity_ad15_20250728_20260728_20260729.json`
  (SHA-256
  `164a912f4c5ccef24173d128a5e4debb5ddfabd171c5e6699716fdb40ffaf631`).
- Source shadow configuration:
  `configs/hypervelocity_source_follow_shadow.toml` (SHA-256
  `e650b9c24e181a0667346aa2ad292ed5183f263c006cca22c9c0f230eba534ef`).
- Risk/holdout evidence remains:
  `data/logs/research/hypervelocity_maker_all_day_conf70_alloc50_lev30_robustness_with_holdout_decision_20260729.json`
  (SHA-256
  `47d7a500855a3a57cf5338dcea8e6f6da9403bd5b3d0c9d344ea95eedf39c762`).

## Confidence, risks, and falsifiers

- Implementation confidence: high, because parity is exact and the full local
  regression suites pass.
- Profitability confidence: medium. The combined replay had PF 1.218 and 8/13
  positive reset blocks, but its Wilson loss-rate upper bound still exceeded
  the empirical break-even loss rate and worst drawdown reached -51.04%.
- Remaining material unknowns: private queue rank, unseen forward regime mix,
  websocket gaps, and non-stationary liquidation frequency.
- Update toward promotion: a fresh venue-matched shadow window must retain
  exact source labels, show no accounting/parity drift, and accumulate enough
  resolved trades to narrow the loss-rate interval below break-even.
- Falsification: repeated source-label disagreement, missed/duplicated entry
  pulses, ledger/TUI divergence, materially worse fill timing than replay, or
  forward losses/drawdown outside the replay distribution rejects or revises
  the candidate.

## Cutover boundary

Do not reset or replace the existing backend implicitly. A fresh source-follow
shadow epoch requires explicit user direction because it changes the active
strategy profile and comparison baseline. It remains no-submit and cannot arm
live trading.
