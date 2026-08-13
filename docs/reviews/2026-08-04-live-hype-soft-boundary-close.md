# Live HYPE soft-boundary close — 2026-08-04

## Outcome

The live HYPE breakout-onset long closed successfully at its configured
eight-hour soft maximum hold. The backend selected exit because the completed
11:30 EDT evaluation was no longer a breakout and did not meet the fixed
regime-support threshold for extension. The venue verified the position flat.

Confidence is high for the lifecycle accounting because the entry, exit,
fees, funding, flat reconciliation, and controller decision are all present in
the authoritative live ledger. Post-exit continuation remains censored until
future completed candles arrive.

## Authoritative lifecycle

- Lifecycle: `HYPE:509645894962`
- Strategy: `hype_breakout_onset_bidirectional_v1`
- Side and size: long `0.45 HYPE`
- Entry: `54.625` at venue timestamp `1785828615468`; entry OID
  `509645894962`
- Exit: `55.189` at venue timestamp `1785857422650`; exit OID
  `509943981546`
- Exit reason: `maximum_hold_seconds`
- Holding time: `28,807,182 ms` (about 8h 00m 07s)
- Gross closed PnL: `+$0.253800`
- Total lifecycle fees: `$0.021347`
- Funding: `-$0.002411`
- Net PnL: `+$0.230042`
- Entry margin: `$4.905541`
- Net return on margin: `+4.6894%`
- Underlying price return: `+1.0325%`

The entry fill was 4.3917 bps better than the recorded reference. The exit was
1.8116 bps adverse to its reference. These are observed venue values rather
than simulated friction.

## Exit decision

At the soft boundary, provider telemetry reported completed 5m `RANGE`, no
new breakout onset, and `5m_not_breakout`. Canonical structure support was
`0.1667` versus the fixed `0.5` extension threshold. The controller therefore
recorded `outcome=exit`; no discretionary or TUI-authored close occurred.

Entry structure support was `1.0`, while exit structure support was `0.1667`.
The component stance moved from aligned at entry to opposing at exit. These
regime values supplied the already-configured maximum-hold decision context;
they were not retroactively fitted to this trade.

## Path capture

- Completed holding candles: 479
- MFE: `213.6384 bps`
- MAE: `27.2769 bps`
- Realized gross return: `103.2494 bps`
- Gross MFE capture: `48.3290%`
- Peak giveback: `110.3890 bps`

The exit was profitable but captured less than half of observed MFE. This is
one trade, not proof of a different timer or trailing-exit edge. The one-hour
post-exit paths will resolve automatically and can show whether the soft exit
avoided reversal or abandoned continuation.

## Current aggregate context

Compatible-profile HYPE history now contains five closed trades: 4W/1L,
`+$1.234701` net, PF `6.5141`, with both long and short represented. This is a
small, serial sample over about 41.75 hours; its largest winner supplies 61.7%
of gross profit. It remains descriptive and does not override the negative
deployed-shape historical replay.

The full compatible portfolio has ten closed trades: 7W/3L, `+$1.257135`, PF
`3.4063`. BTC remains open and protected. No strategy parameter, allocation,
or runtime process changed during this reconciliation.

## Falsifiers and next evidence

- A venue fill or account-history disagreement would invalidate the stated
  price, fee, funding, or net result.
- A non-flat HYPE position or surviving reduce-only order would invalidate the
  lifecycle closure; the observed reconciliation reports flat with no open
  HYPE orders.
- Repeated fresh trades showing higher net capture under a different
  predeclared exit rule would update the current timer. One favorable close or
  one large MFE giveback is insufficient.
- Resolved post-exit paths will update whether this exact close was early or
  late relative to the next 5, 15, 30, and 60 minutes.

