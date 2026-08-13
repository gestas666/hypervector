# Hypervelocity +7% Peak Observer Evidence

Date: 2026-07-29

## Problem restatement

The unchanged Hypervelocity strategy holds one 70%-margin, 40x isolated BTC
position until its +8% gross-margin target. Venue replay showed that a position
can approach the target and then reverse into liquidation. The question is
whether a source-derived peak lock can reduce those reversals without clipping
enough eventual targets to lower net returns.

The candidate is report-only. It does not change entries, targets, sizing,
regime classification, portfolio state, order commands, or model authority.

## Frozen candidate

- Candidate: `source_peak_activation7_v1`.
- Sample authentic Hyperliquid marks every five seconds.
- Arm after +7% gross margin PnL at 40x.
- Lock 55% of the highest observed gross-margin PnL.
- Ratchet no more than once per 60 seconds and only after a stop improvement of
  at least 0.05% of entry price.
- Price a hypothetical long exit at fresh best bid and a short exit at fresh
  best ask; include the configured taker fee.
- Missing or stale BBO produces `peak_observer_trigger_unpriced`, not a fill.
- `execution_authority="none"`, `submitted=false`, and
  `place_attempted=false` are durable invariants.

The observer configuration is deliberately outside `portfolio_spec` and its
fingerprint. Switching observe/off cannot create a portfolio migration or alter
execution identity.

## Development evidence

Across twelve independently reset development blocks, the unchanged control
had 59 fills, 55 targets, three liquidations, one open position, aggregate PnL
of $17,577.90, and -74.53% worst drawdown. The +7% candidate had the same entry
stream with 53 targets, two liquidations, three peak exits, one open position,
aggregate PnL of $19,086.10, and -58.14% worst drawdown.

These are reset-block totals, not one continuously compounded portfolio. The
candidate improved aggregate PnL by $1,508.20 and worst drawdown by 16.39
percentage points, but it remains development evidence.

The untouched April 18-28 window produced one filled target and four canceled
entries. Control and candidate both ended at $10,471.90. This holdout is
non-inferior but statistically uninformative because the observer never armed.

## Implementation validation

The pure observer covers long/short arithmetic, activation, retained peak,
ratchet cooldown, minimum price movement, no widening, five-second cadence,
stale evidence, adverse-BBO price, taker fee, lifecycle end, and strict restart
restoration. The normal backend session restores an armed observer without a
duplicate start.

Observer-on and observer-off bridges produced identical controller state,
account snapshot, execution records, and actual open position. Focused
verification passed 104 Python tests; downstream liquidation-evidence tests
passed 10 tests; Ruff and formatting passed; all 33 Rust/TUI integration tests
passed.

The active backend retained its original 2026-07-29 06:14:18 EDT start time
through implementation. It loaded the earlier partial-close accounting fix but
predates the observer configuration and therefore emits no observer rows. It
must not be restarted until flat.

## Forward acceptance and falsification

Initial forward evidence is inconclusive until both conditions are met:

- at least 50 completed venue-matched shadow positions across multiple market
  regimes; and
- at least 10 complete-coverage positions where the +7% observer arms.

These are engineering evidence thresholds, not a guarantee of statistical
significance. Report interim counts without promoting the rule.

For every armed lifecycle, compare the priced hypothetical exit against the
actual remaining lifecycle after fees and funding. Reject the candidate if the
sum of hypothetical net outcomes is no better than actual outcomes, if fresh
BBO coverage is materially incomplete, or if avoided reversals do not exceed
clipped target upside.

The observer does not simulate counterfactual re-entry after a hypothetical
exit. Before promotion, replay the recorded live venue tape through a stateful
twin that applies the hypothetical exit and subsequent normal entry rules.
Reject promotion if that full-path twin is inferior to the unchanged control.

## Uncertainties and failure modes

- Public L2 cannot reveal private queue rank; entry fills remain trade-through
  estimates rather than guaranteed venue fills.
- Five-second mark sampling can miss intrainterval peaks or stop crossings.
- A local exit comparison omits opportunity cost until the stateful twin is run.
- The development improvement could be concentrated in one April 11 reversal.
- At 40x and 70% allocation, one remaining liquidation can dominate many target
  wins; a high win rate alone is insufficient evidence.

Confidence is high that the observer is non-authoritative and causally priced.
Confidence that +7% improves risk-adjusted forward economics is medium-low
until the declared forward sample exists. Consistently inferior armed-lifecycle
outcomes would falsify the candidate immediately.
