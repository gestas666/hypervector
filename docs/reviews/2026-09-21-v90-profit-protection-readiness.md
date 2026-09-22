# V90 profit protection, sizing and transition readiness

Date: 2026-09-21. Execution authority: none. V90 is a prepared candidate; live
activation requires the final operator decision. The account is flat, trading
is stopped, and the completed transition drain remains in place.

## Requirement and implemented behavior

The operator's repeated requirement to protect open profit is an exit-design
constraint. Earlier wording that generic profit locks were "rejected by the
data" was too broad: three tight policies on nine eligible trades did not
justify dismissing the requirement. It also used an intraminute stop-price proxy
that differs from the live controller's completed-minute/current-market exit.

The candidate uses a distinct strategy identity:
`hourly_donchian_20_10_atr20_profit_lock_bidirectional_v2`, for SOL, SNDK and
BRENTOIL, both directions. Entries and hourly recipe exits match Donchian 20/10.
Its frozen profit-lock contract activates at **100 bps (1%) favorable movement**,
sets a **25-bps gross entry floor**, and trails **50 bps (0.5%) behind the best
completed-minute price**. The prior completed minute's stop is tested before
updating it with the current minute's high/low. A crossing journals a durable
close decision before returning a current-market close action. Restart restores
the bound plan and recorded decision; it does not invent a new entry policy.
Initial venue protection, hourly recipe exits and the 24-hour fallback remain.
BTC retains its existing 60-bps take-profit and 60-bps initial stop.

This is a software exit, **not a venue-resident trailing stop or guaranteed
realized floor**. A completed minute plus polling/processing/transport delay can
cross the nominal floor before execution. Missing candle history emits degraded
telemetry and withholds an unproven lock decision; initial venue protection
remains. An outage, thin book, gap, fees or funding can also consume the floor.

## Evidence and confidence

High confidence in the recorded givebacks, recovered-path accounting and tested
causal behavior. Low confidence in future returns or an executable profit floor.
A mismatched lifecycle, corrected fills/candles, live replay mismatch, or measured
slippage beyond the assumptions would update this assessment.

The frozen comparison is documented in
`docs/plans/2026-09-21-v90-profit-protection.md`. It compares unchanged exits and
three predefined policies, without fitting additional thresholds. All 28 closed
V89 lifecycles were included in path eligibility. Immutable live candle records
and verified startup parquet files recover **27 complete paths**. One SNDK
lifecycle (`542326864971`, actual +$23.50) has 2,059 missing minutes and is withheld
from every policy and its matched baseline. No new market data was fabricated.
The prior checkpoint's bounded current-run window understated available history.

The new replay shares the live trigger engine but values execution at the
completed trigger minute's close, with 5/15-bps adverse price stresses, recorded
entry fees, exit fee rate and funding through the decision boundary. It does not
reuse a later actual fill's favorable slippage ratio. These are delayed-execution
proxies, not reconstructed executable quotes; actual polling latency is not
measured by the stress assumption. The original nine-trade evidence remains
historical and uses a different sample/fill model.

| Activation / floor / trail | Complete paths | Triggers | Actual net, same paths | Proxy net, 5 bps | Proxy net, 15 bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged | 27 | — | -$10.81 | -$10.81 | -$10.81 |
| 60 / 15 / 30 bps | 27 | 14 | -$10.81 | +$3.07 | -$3.92 |
| **100 / 25 / 50 bps — proposed** | 27 | 11 | -$10.81 | -$3.80 | -$9.29 |
| 150 / 35 / 75 bps | 27 | 8 | -$10.81 | -$11.95 | -$15.97 |

The proposed rule improved eight outcomes, reduced three and left sixteen
unchanged in this sample. It was chosen before this replay as a moderate
profit-retention preference, not because it maximized the table. Results are
exploratory; these historical paths are not an untouched holdout. The sample
includes old SOL/Brent/SPCX mechanisms and BTC; it is an exit counterfactual on
fixed original entries, **not a full V90 portfolio backtest**. It does not model
new entries made possible by earlier exits, changed capacity, or larger sizing.

| Example, original trade size | Actual net | Proposed proxy net, 5–15 bps |
| --- | ---: | ---: |
| Latest SNDK | -$1.74 | +$3.59 to +$4.09 |
| Latest BRENTOIL | -$0.60 | +$2.63 to +$3.14 |
| Latest SOL | +$1.76 | +$1.89 to +$2.39 |
| Earlier SNDK winner `547778613726` | +$27.25 | +$4.86 at 5 bps |
| Earlier SNDK winner `548912302537` | +$25.30 | +$3.92 at 5 bps |

The two cut winners make the trade-off concrete. The proposal addresses explicit
profit-taking; it cannot simultaneously promise to preserve every later trend.

## Corrected sizing

Unsigned venue preflight at **14:50:36 UTC** confirms flat/order-free state,
ledger reconciliation and technically valid sizing at equity **$4,870.28**.
Visible depth covered both sides at the sampled sizes. A single book snapshot
does not establish future execution quality or replace the older depth stress.

| Active route | Leverage | Proposed notional | Initial gross stop exposure |
| --- | ---: | ---: | ---: |
| BTC long | 10x | $535.73 | $3.21 at 60 bps |
| SOL both directions | 8x | $506.51 | $1.01–$12.66 at 20–250 bps |
| SNDK both directions | 8x | $1,948.11 | $3.90–$48.70 at 20–250 bps |
| BRENTOIL both directions | 8x | $584.43 | $1.17–$14.61 at 20–250 bps |

ETH, HYPE and SPCX remain observed with no automatic execution allocation.
Combined active margin is 8.9% of equity (about $433.46). At all four initial
stop distances' maxima, gross stop exposure is about $79.19 before gaps, fees or
funding. This is not a hard maximum loss. SNDK's notional is about 3.9x its old
$500 cap. Its size increase remains a risk preference, not a validated
performance improvement. Uptime repair does not justify "no added risk per
trade" for this allocation change. The exact trade-frequency multiplier remains
unvalidated.

| Choice | Benefit | Cost / uncertainty |
| --- | --- | --- |
| Keep trading stopped | No new market exposure | Missed opportunities; no forward validation |
| Protected V90 with prior SNDK cap | Implements exits while limiting the size change | Different candidate fingerprint and revised approval required |
| Proposed protected V90 allocation | Implements requested exit behavior and growth allocation | Larger SNDK exposure; simultaneous changes complicate attribution |

No performance-based rejection gate is introduced. The final operator decision
is the exact protected candidate and allocation, with the above limitations.

## Validation and launch boundary

Candidate fingerprint:
`b34fd819076cd8b0cf143d9d4cae9a0e6637a508daf2ed35f6570cfb245025d2`.
V89 retains its original fingerprint. New tests cover strict protection binding,
parameter drift, legacy contract isolation, identical entry signals, both-side
causal exits, durable decision replay, coverage gaps, delayed fills and costs.
The disarmed production observer completed a bounded run using this candidate;
all events reported `execution_mode=observe`, `execution_authority=none`, and
`live_armed=false`.

The preflight correctly refuses a live transition for two outstanding operational
steps: final approval remains a draft, and the completed drain has not been
archived/cleared. The drain archive command passed its non-mutating preview.
Do not describe this as a fully activated or currently trading profile.

Prepared V90 supervisor/checkpoint definitions and activation/rollback steps are
in `docs/proposals/v90-supervisor-20260920/v90-activation.md`. These definitions
are not loaded. Read-only observer, watchdog and V89-following checkpoint are
loaded; observer capture survived restart with its earlier bytes preserved.
The backend watchdog's stopped/stale alerts are expected during the explicit hold.

Evidence: `data/logs/research/v90_profit_protection_20260921/` in the main checkout;
focused tests, coverage and observe smoke evidence in
`data/logs/research/v90_monitoring_capture_20260920/` in the prepared checkout.

## Code review and verification record

Self-review traced the new identity through configuration validation, default
collector selection, source clocks, canonical telemetry, execution-plan binding,
full terminal-hold history, durable profit-lock decisions and pending-transition
validation. No signed-order placement/retry code was changed by the profit-lock
candidate; existing close routing supplies the order behavior. No reproducible
regression remains in the reviewed changed paths. This is bounded evidence, not
an assertion that every possible defect has been excluded.

- Exit/configuration/transition/sizing regressions: **183 passed**.
- Focused coverage run: **46 passed**; new delayed-exit calculation and strict
  hourly contract have **100% measured line and branch coverage**. Evidence table
  is fully covered; the shared hourly publisher has 96.1% line / 83.3% branch
  coverage in this selection (uncovered branches predate this change).
- Test-first failures reproduced missing protected behavior and delayed-exit
  handling; the package test also detected stale recommendation hashes before
  they were refreshed. The final package validates its exact body while the
  pending header still refuses live transition.
- Coverage initially failed during dotted-module source discovery with a NumPy
  double-import error; using a filesystem coverage source completed successfully.
  This was a test instrumentation failure, retained in the logs.
- Earlier maintenance: **395 passed, 4 network tests deselected**; disarmed
  supervisor kill/restart/hold acceptance passed. No armed kill test was run.
- Full-suite baseline remains as documented in the maintenance acceptance:
  two existing failures reproduced in the original checkout; no claim of a
  completely green full Python suite. Rust previously passed 655 tests, with
  23 ignored. No Rust/UI code was changed by this profit-lock addition.

Final draft-body/lineage/service/history package checks: **3 passed**. Additional
monitoring, restart, capture, archive and expanded hourly idle-poll regressions:
**136 passed**. Ruff check/format, whitespace and prepared plist syntax passed.
A final signed activation and forward fill/performance validation remain outside
these preparation checks. Candidate source is copied into the flat/stopped main
checkout only with an exact backup; the V90 launch definitions remain unloaded.
