# SOL live soft-hold extension review

## Decision

At `2026-08-08T11:35:06.588Z`, the v25 live controller crossed the SOL
HT-Breakout lifecycle's eight-hour soft deadline. It durably recorded
`outcome=extend` with structural alignment `1.0`, above the configured `0.5`
threshold. Both the bound provider and canonical context classified 1m, 5m,
15m, and primary structure as `TREND_UP`.

This was an authoritative live-controller decision, not a TUI inference. No
order was submitted because the outcome was to continue holding. SOL remained
long `1.0` with owned stop `512630736897`; the hard deadline remains 24 hours
after the persisted runtime open time.

## Economic state at the boundary

The checkpoint shortly after the decision showed entry `74.457`, mark
`75.225`, approximately `+103.15` bps current directional return, `+153.51`
bps MFE, and `50.36` bps peak giveback. Marked lifecycle PnL after entry fee
and funding was `+$0.728359`; estimated net if closed immediately after another
measured taker fee was `+$0.695862`.

The current venue stop remains below entry at `73.861344`, so none of that open
profit is protected. All three predeclared profit-lock challengers had already
triggered before the soft boundary. That does not prove they are better:
resolved all-time mechanism evidence has often penalized early locks, and this
live lifecycle is still open.

## Interpretation

The canonical provider reported `regime_not_admitted` for a new entry because
there was no hourly cross and its entry-specific 5m admission rule was false.
That is not contradictory to the hold extension. The maximum-hold controller
uses directional structural states for an existing position, and every
weighted state was aligned long at the decision timestamp.

The extension decision is therefore implementation-correct under the bound
v25 policy. Whether it is economically better remains unresolved. The valid
comparison is the eventual live close versus:

- the friction-adjusted soft-boundary exit;
- the three predeclared profit-lock paths; and
- the unchanged original-stop path.

No mid-trade policy change is supported by one open observation.

## Confidence and falsification

Confidence is high that the controller executed the configured rule and
journaled it exactly once: the raw live ledger, checkpoint projection, open
position, and stop identity agree. Confidence is low on the extension's edge
until the lifecycle resolves.

A missing/changed durable decision, lost stop, unexplained close, or eventual
friction-adjusted result materially below the predeclared alternatives would
falsify the relevant claim and update the next flat-boundary recommendation.
