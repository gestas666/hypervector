# ETH/SOL Bidirectional 5m/15m Tuning Review

## Decision

Do not create an observe-only provider from the tested BBWP-release/fixed-RR
family. The complete development surface was retained, but none of the 12
development-selected candidates produced positive nominal and stressed results
across validation and pseudo-holdout.

This is a family-level falsification under the declared data, timing, and cost
contract. It is not evidence that ETH or SOL cannot support another strategy.

## Evidence contract

- Venue: Hyperliquid one-minute bars and hourly funding.
- Window: `2025-07-28T00:00Z..2026-07-28T00:00Z`.
- Development: `2025-07-28..2026-01-28`.
- Validation: `2026-01-28..2026-04-28`.
- Pseudo-holdout: `2026-04-28..2026-07-28`.
- Execution decisions: completed 5m bars with completed 15m context.
- Friction: 13 bps nominal and 20 bps stress round trip.
- Portfolio: $15,000, isolated 5x, 0.5% equity risk, 70% maximum margin.
- Search: 1,728 trials, 432 per asset/side; no losing or zero-trade trial was
  removed from the evidence ledger.
- Selected replay: three development-ranked candidates per asset/side, 72
  one-minute replay cells total.
- Execution authority: `none`.

Source quality was complete at 525,600 minute rows and 8,760 funding events per
asset. ETH used 164 explicit gap-fill rows; SOL used 211. These rows are visible
in provenance rather than silently hidden.

## Reconciled result

| Asset/side | Best selected later nominal net | Later trades | Validation PF | Pseudo PF | Result |
|---|---:|---:|---:|---:|---|
| ETH long | -$783.00 | 81 | 0.65 | 0.74 | research only |
| ETH short | -$949.72 | 99 | 0.93 | 0.56 | research only |
| SOL long | -$420.96 | 40 | 0.70 | 0.83 | research only |
| SOL short | -$224.28 | 34 | 1.20 | 0.40 | research only |

All 1,800 result rows and their DuckDB trade rows reconciled with zero count or
net-PnL mismatches. The corrected v2 artifact contains no embedded trades and is
2.6 MB; complete trade rows remain in DuckDB.

## Baseline comparison

The existing low-timeframe baseline's strongest relevant cell remains SOL long
`trend_expansion_v1 / ema_alignment_exit`:

| Segment | Net | Trades | PF |
|---|---:|---:|---:|
| Development | +$631.44 | 34 | not used for conclusion |
| Validation | +$585.43 | 18 | 1.46 |
| Pseudo-holdout | -$142.45 | 19 | 0.91 |

Its combined later-window net is +$442.98, but the negative pseudo-holdout means
it is not yet stable enough to infer a forward edge. It nevertheless outperforms
the fixed-RR challenger and is the narrower, higher-information next diagnostic.

## Defects found and corrected

The first v1 selection ranked temporal month counts before net profitability.
That allowed negative development trials to outrank positive alternatives. The
rank key now places positive development net ahead of month stability while
retaining every negative trial in the report.

The first v1 JSON also embedded 174,205 trade rows and grew to 188 MB. Trade rows
were already stored in DuckDB. V2 removes them from JSON, preserves v1 as an
audit artifact, and links its reused development evidence by immutable run ID.

## Next experiment

Decompose SOL-long `trend_expansion_v1 / ema_alignment_exit` by month, exit
reason, holding time, fees/funding, and decision-time regime. Then test a bounded
exit/context neighborhood around that baseline rather than changing its entry
and exit simultaneously.

Success means improved pseudo-holdout net and PF without reversing development
or validation, under 20 bps stress and exact one-minute path replay. Failure is
retained evidence and retires this SOL-long mechanism from forward observation.

No provider, config execution scope, or live profile changes are authorized by
this review.

## Follow-up falsification

The post-hoc SOL-long exit surface kept the original entry and varied only ATR
stop width and maximum hold. Wider stops and 6h/8h holds improved development
and validation, but every selected candidate lost in every pseudo-holdout
month. The best selected pseudo PF was 0.32. This falsified the hypothesis that
the original 4h hold alone caused the degradation.

Canonical regime attribution showed `BREAKOUT` trades outperforming
`TREND_UP` trades in the stored ledger, but an exact one-minute replay was
required because filtering completed trades changes portfolio sequencing. The
exact results were:

| Arm | Development 13/20 bps | Validation 13/20 bps | Pseudo 13/20 bps |
|---|---:|---:|---:|
| All baseline signals | +$631 / -$12 | +$585 / +$220 | -$142 / -$483 |
| Canonical 5m BREAKOUT only | +$1,554 / +$1,036 | +$887 / +$534 | -$174 / -$392 |
| Canonical 5m TREND_UP only | -$724 / -$899 | -$373 / -$395 | -$299 / -$436 |

The BREAKOUT arm's later failure means canonical regime is useful telemetry but
does not rescue this entry mechanism. ETH and SOL therefore remain unarmed.
Further historical threshold search on this pseudo-holdout would increase
multiple-testing bias; the next evidence for this mechanism would need a frozen
forward observer or a genuinely different strategy hypothesis.
