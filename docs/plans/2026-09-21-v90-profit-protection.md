# V90 profit protection and launch readiness

Frozen proposal scope: 2026-09-21, before the new replay. Authority: preparation
and read-only maintenance approved; live activation remains pending. The account
is flat and the completed transition drain remains installed.

## Requirement

The operator requires an explicit profit-taking rule instead of surrendering
large open gains while waiting for an hourly recipe or maximum-hold exit.
Protect gains on both sides of every active hourly V90 route. Preserve BTC's
existing 60-bps take-profit. Preserve initial protective stops, recipe exits,
transition drain, reduce-only execution and durable lifecycle identity.

The proposed default is completed-minute trailing protection: activate after
100 bps (1%) favorable price movement, a 25-bps gross entry floor, and a trail
50 bps behind the best completed-minute price. It is chosen as a concrete
profit-retention preference, not a fitted claim of higher returns. The prior
minute's stop is evaluated before the current minute updates the high/low.
Execution occurs at the current market after detecting the completed crossing;
this is not a venue-resident trailing stop or a guaranteed floor. A backend
outage, missing candles, minute reversal, liquidity gap or fees can reduce the
realized protection. BTC's native target is a separate existing mechanism.

## Bounded comparison fixed before evaluation

Compare unchanged exits, existing tight (60/15/30 bps), proposed (100/25/50), and
wider (150/35/75). Do not optimize beyond these three in this assessment. Include
all 28 closed V89 lifecycles in the cohort, report each unavailable path, include
winners and losers, fees and funding, and distinguish current-route relevance.
The old 9-trade result is evidence against three tight parameters, not evidence
against the operator's profit-protection requirement.

Recover observed candles from the immutable ledger/startup inputs and unsigned
public candles where available. Never fabricate missing bars. Use the completed
trigger minute's close and adverse 5/15-bps execution stresses, rather than an
intraminute stop fill, for the new delayed-execution comparison. These are proxy
fills, not reconstructed executable quotes. Historical paths were seen before
this proposal, so results are exploratory; no untouched holdout is claimed.
Report aggregate and per-trade PnL, saved losses, cut winners, and missing paths.

## Implementation and validation

1. Introduce a distinct protected hourly Donchian 20/10 provider identity and
   strict frozen execution contract; leave V89 and other provider identities
   unchanged. Reuse the tested completed-bar controller and durable plan.
2. Write failing tests for candidate parsing, wrong/missing protection rejection,
   signal parity, long/short exits, fees/latency replay, restart recovery and
   pending live-approval refusal; then implement and run relevant regressions.
3. Update the V90 config, evidence catalog, approval draft, scope replacements,
   profile fingerprint, sizing review and deployment/rollback instructions.
4. Run unsigned candidate preflight, configuration/generation checks and a
   disarmed observer smoke test. Review code and source hashes before copying
   candidate changes into the flat/stopped runtime checkout with backups.
5. Leave live activation pending. Readiness means a concrete tested candidate,
   not a promise of profitability. Flag every remaining technical blocker and
   the final operator decision explicitly; no performance-based implicit gate.

## Trade-offs and rollback

Unchanged exits have no new engineering risk but leave the requested behavior
unaddressed. Tight protection reacts earlier and cuts more trends. The proposed
rule protects later and allows 0.5% retracement. Wider protection allows more
movement and larger giveback. All may sacrifice later winners. V90 sizing remains
an explicit risk preference, evaluated separately from profit protection; an
exit change does not validate increasing SNDK size. Rollback requires flat state,
exact source/config backups, a reconciled ledger and renewed approved identity.
